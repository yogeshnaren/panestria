import {useEffect, useRef, useState, type FormEvent} from 'react';
import {Denied, json} from './client';
import type {components, operations} from './schema';

type Receipt = components['schemas']['AskReceipt'];
type Answer = components['schemas']['AskAnswer'];
type Submission = operations['ask_question_v1_ask_post']['requestBody']['content']['application/json'];
type Phase = 'IDLE'|'POSTING'|'UNKNOWN'|'ACTIVE'|'TERMINAL';
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const terminal = (state: Receipt['state']) => ['COMPLETED','CANCELLED','UNAVAILABLE'].includes(state);
function validate(value: Receipt, id: string): Receipt {
  if(value.request_id !== id || !['PREPARED','RUNNING','COMPLETED','CANCELLED','UNAVAILABLE'].includes(value.state) ||
      value.offline !== true || value.response_retained !== false || !Array.isArray(value.sources) ||
      (value.usage !== null && (typeof value.usage !== 'object' || Array.isArray(value.usage)))) throw new Error('Unconfirmed receipt.');
  return value;
}

export function OfflineAsk({project, csrf, deny}: {project:string, csrf:string|null, deny:()=>void}) {
  const [question,setQuestion] = useState('');
  const [id,setId] = useState('');
  const [lookup,setLookup] = useState('');
  const [receipt,setReceipt] = useState<Receipt|null>(null);
  const [answer,setAnswer] = useState<string|null>(null);
  const [phase,setPhase] = useState<Phase>('IDLE');
  const [reading,setReading] = useState(false);
  const [notice,setNotice] = useState('Ready for an offline question.');
  const active = useRef(false), commands = useRef(false), epoch = useRef(0);
  const post = useRef<AbortController|null>(null);
  const denyRef = useRef(deny); denyRef.current = deny;
  useEffect(()=>{
    const clear = () => {
      epoch.current++;post.current?.abort();post.current=null;setQuestion('');setAnswer(null);
      if(active.current) {setPhase('UNKNOWN');setNotice('Page left during a request. Inspect its receipt before submitting again.');}
    };
    window.addEventListener('pagehide',clear);
    return ()=>{epoch.current++;post.current?.abort();window.removeEventListener('pagehide',clear);};
  },[]);
  const bytes = new TextEncoder().encode(question).length;
  const unresolved = phase === 'POSTING' || phase === 'UNKNOWN' || phase === 'ACTIVE';
  async function submit(event:FormEvent) {
    event.preventDefault(); if(!csrf || active.current || commands.current || !question.trim() || bytes>4096) return;
    active.current = true;
    const generation = ++epoch.current, requestId = crypto.randomUUID(), controller = new AbortController();
    post.current = controller;
    setId(requestId);setLookup(requestId);setReceipt(null);setAnswer(null);setPhase('POSTING');
    setNotice('Running offline. Keep this request ID to inspect or cancel the same request.');
    const body:Submission = {request_id:requestId,project_id:project,question,privacy_label:'RESTRICTED',
      offline:true,retain_response:false,context_tokens:2048,max_output_tokens:128,deadline_seconds:60};
    try {
      const result = await json<Answer>('/v1/ask',controller.signal,body,csrf,65000);
      if(generation !== epoch.current) return;
      validate(result,requestId);setReceipt(result);
      if(result.state==='COMPLETED' && typeof result.text==='string' && !result.replayed_receipt) setAnswer(result.text);
      active.current = !terminal(result.state);setPhase(active.current?'ACTIVE':'TERMINAL');
      setNotice(result.state==='COMPLETED' ? 'Completed. Answer text exists only in this page; the server retains a receipt.' : 'Canonical receipt received.');
    } catch(error) {
      if(generation !== epoch.current) return;
      setAnswer(null);
      if(error instanceof Denied) {denyRef.current();return;}
      setPhase('UNKNOWN');setNotice('UNCONFIRMED. Inspect this request ID before starting another question. No automatic retry was sent.');
    } finally {if(generation===epoch.current) post.current=null;}
  }
  async function inspect(event?:FormEvent) {
    event?.preventDefault();if(commands.current) return;
    const requestId = (unresolved?id:lookup).trim().toLowerCase();
    if(!uuid.test(requestId)) {setNotice('Enter a request UUID.');return;}
    commands.current=true;setReading(true);const generation=epoch.current;
    try {
      const value = validate(await json<Receipt>(`/v1/ask/${requestId}`,AbortSignal.timeout(8000)),requestId);
      if(generation!==epoch.current) return;
      if(requestId!==id) setAnswer(null);
      setId(requestId);setLookup(requestId);setReceipt(value);
      // A successful POST can still carry the one transient answer. Reading a
      // completed receipt must not discard that pending response.
      if(!post.current || value.state==='CANCELLED' || value.state==='UNAVAILABLE') {
        if(post.current) {epoch.current++;post.current.abort();post.current=null;}
        active.current=!terminal(value.state);setPhase(active.current?'ACTIVE':'TERMINAL');
      }
      setNotice(terminal(value.state)?'Canonical terminal receipt. Reloaded receipts cannot recover answer text.':'Canonical request is active. Inspect again or cancel; no new inference was submitted.');
    } catch(error) {
      if(generation!==epoch.current) return;
      if(error instanceof Denied) {denyRef.current();return;}
      setNotice('Receipt unconfirmed or unavailable in this project. No request was submitted or retried.');
    } finally {commands.current=false;setReading(false);}
  }
  async function cancel() {
    if(!csrf || !id || commands.current || !active.current) return;
    commands.current=true;setReading(true);const generation=epoch.current;
    try {
      const result = await json<components['schemas']['AskCancellation']>(`/v1/ask/${id}/cancel`,AbortSignal.timeout(8000),{},csrf);
      if(generation!==epoch.current) return;
      if(result.request_id!==id || !['PREPARED','RUNNING','COMPLETED','CANCELLED','UNAVAILABLE'].includes(result.state)) throw new Error('Unconfirmed cancellation.');
      if(terminal(result.state)) {
        epoch.current++;post.current?.abort();post.current=null;active.current=false;setPhase('TERMINAL');setAnswer(null);
        setReceipt(null);setNotice(`Canonical request state: ${result.state}. Inspect the receipt for details.`);
      } else {setPhase('ACTIVE');setNotice('Cancellation has not reached a terminal state. Inspect the same request.');}
    } catch(error) {
      if(generation!==epoch.current) return;
      if(error instanceof Denied) {denyRef.current();return;}
      setNotice('Cancellation UNCONFIRMED. Inspect this request; cancellation was not assumed.');
    } finally {commands.current=false;setReading(false);}
  }
  function newQuestion() {
    if(active.current || commands.current || post.current) return;
    epoch.current++;setId('');setLookup('');setQuestion('');setAnswer(null);setReceipt(null);setPhase('IDLE');setNotice('Ready for an offline question.');
  }
  return <section aria-label="Offline Ask"><h2>Offline Ask</h2>
    <p>Uses this workstation’s configured local model. RESTRICTED · offline · no response retention · no profile context.</p>
    <p role="status" data-testid="ask-notice">{notice}</p>
    {!csrf && <p>Pair again to submit or cancel. Existing receipts remain readable in this session.</p>}
    <form onSubmit={submit}><label htmlFor="ask-question">Question</label>
      <textarea id="ask-question" value={question} onChange={e=>setQuestion(e.target.value)} rows={5} maxLength={4096}
        autoComplete="off" spellCheck={false} disabled={unresolved || phase==='TERMINAL'} required/>
      <p className="muted">{bytes} / 4096 UTF-8 bytes. Output is limited to 128 tokens; deadline 60 seconds.</p>
      <div className="actions"><button disabled={!csrf || unresolved || phase==='TERMINAL' || !question.trim() || bytes>4096}>Ask offline</button>
        {id && <button type="button" onClick={()=>void cancel()} disabled={!csrf || !unresolved || reading}>Cancel request</button>}
        {phase==='POSTING' && <button type="button" onClick={()=>post.current?.abort()}>Stop waiting</button>}
        {phase==='TERMINAL' && <button type="button" onClick={newQuestion} disabled={reading}>New question</button>}</div>
    </form>
    {phase==='POSTING' && <p className="muted">Stop waiting disconnects this response. It does not confirm cancellation; inspect the same receipt afterward.</p>}
    {id && <p>Request ID <code data-testid="ask-id">{id}</code></p>}
    <form onSubmit={inspect}><label htmlFor="ask-receipt">Recover receipt by request ID</label>
      <div className="actions"><input id="ask-receipt" className="receipt-id" value={lookup} onChange={e=>setLookup(e.target.value)}
        disabled={unresolved} autoComplete="off" spellCheck={false} required/>
        <button disabled={reading || !(unresolved?id:lookup).trim()}>Inspect receipt</button></div></form>
    {receipt && <div aria-label="Ask receipt"><p>Canonical state: <strong data-testid="ask-state">{receipt.state}</strong></p>
      <p>Model <code>{receipt.model_ref}</code> · privacy {receipt.privacy_label} · {receipt.code??'no error code'}</p>
      <p>Context pack <code>{receipt.context_pack_id}</code> · trace <code>{receipt.trace_id}</code></p>
      <h3>Measured usage</h3>{receipt.usage===null?<p>Unavailable: no completed usage measurement.</p>:<pre>{JSON.stringify(receipt.usage,null,2)}</pre>}
      <p>Source context IDs: {receipt.sources.map((source,i)=><code key={i}>{String(source.source_id??source.id??'unavailable')} </code>)}</p>
    </div>}
    {answer!==null && <div aria-label="Local answer"><h3>Local answer</h3><pre data-testid="ask-answer">{answer}</pre></div>}
  </section>;
}
