import {useEffect,useRef,useState,type FormEvent} from 'react';
import {Denied,json} from './client';
import type {components,operations} from './schema';
type Template = components['schemas']['ResearchIntakeView'];
type Receipt = components['schemas']['ResearchStagingView'];
type Submission = operations['stage_v1_mission_research_questions_post']['requestBody']['content']['application/json'];
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export function ResearchIntake({owner,project,csrf,deny}:{owner:string,project:string,csrf:string|null,deny:()=>void}) {
  const [template,setTemplate]=useState<Template|null>(null),[question,setQuestion]=useState(''),[confirmed,setConfirmed]=useState(false);
  const [goal,setGoal]=useState(''),[lookup,setLookup]=useState(''),[receipt,setReceipt]=useState<Receipt|null>(null);
  const [notice,setNotice]=useState('Reading owner-selected template…'),[pending,setPending]=useState(false),[uncertain,setUncertain]=useState(false);
  const busy=useRef(false), controller=useRef(new AbortController()),denyRef=useRef(deny);denyRef.current=deny;
  useEffect(()=>{
    const current=controller.current;
    void json<Template>('/v1/mission/research/intake',current.signal).then(value=>{
      if(value.owner_id!==owner || value.project_id!==project || value.execution_authority!=='NONE' || !/^[0-9a-f]{64}$/.test(value.template_sha256)) throw new Error('Unconfirmed template');
      if(!current.signal.aborted) {setTemplate(value);setNotice('Review the exact contract and bounds before staging a PUBLIC question.');}
    }).catch(error=>{if(current.signal.aborted)return;if(error instanceof Denied)denyRef.current();else setNotice('Template unavailable. No question can be submitted.');});
    const clear=()=>{setQuestion('');setReceipt(null);setConfirmed(false);};window.addEventListener('pagehide',clear);
    return()=>{current.abort();window.removeEventListener('pagehide',clear);};
  },[owner,project]);
  function validate(value:Receipt,id:string) {
    if(value.goal_id!==id || value.owner_id!==owner || value.project_id!==project || value.operation!=='STAGED_NO_EXECUTION' || value.execution_authority!=='NONE' || typeof value.question!=='string') throw new Error('Unconfirmed receipt');
    return value;
  }
  async function submit(event:FormEvent) {
    event.preventDefault();if(!template || !csrf || busy.current || uncertain || receipt || !confirmed || !question.trim() || new TextEncoder().encode(question).length>4096)return;
    busy.current=true;setPending(true);setUncertain(true);const id=crypto.randomUUID();setGoal(id);setLookup(id);setNotice('Staging locally. No network or model execution is requested.');
    const body:Submission={goal_id:id,template_sha256:template.template_sha256,question,public_question:true};
    try {
      const value=validate(await json<Receipt>('/v1/mission/research/questions',controller.current.signal,body,csrf),id);
      if(controller.current.signal.aborted)return;setReceipt(value);setUncertain(false);setNotice('STAGED_NO_EXECUTION. Canonical state confirmed; this operation starts no research.');
    } catch(error) {
      if(controller.current.signal.aborted)return;
      if(error instanceof Denied)denyRef.current();else setNotice('UNCONFIRMED. Inspect this goal ID before any new submission. No automatic POST retry was sent.');
    } finally {busy.current=false;setPending(false);}
  }
  async function inspect(event:FormEvent) {
    event.preventDefault();if(busy.current)return;const id=(uncertain?goal:lookup).trim();if(!uuid.test(id)){setNotice('Enter a goal UUID.');return;}
    busy.current=true;setPending(true);
    try {
      const value=validate(await json<Receipt>(`/v1/mission/research/questions/${id}`,controller.current.signal),id);
      if(controller.current.signal.aborted)return;setGoal(id);setLookup(id);setReceipt(value);setUncertain(false);setQuestion('');setConfirmed(false);setNotice('Canonical retained question inspected. No execution or resubmission.');
    } catch(error) {
      if(controller.current.signal.aborted)return;if(error instanceof Denied)denyRef.current();else setNotice('Question unconfirmed or unavailable in this project. No new submission was sent.');
    } finally {busy.current=false;setPending(false);}
  }
  return <section aria-label="Delegate question"><h2>Delegate · stage a PUBLIC question</h2>
    <p>Local staging only. No search, collection, synthesis, model or worker is started. Later execution requires its own qualified runtime and owner action.</p>
    <p role="status" data-testid="research-notice">{notice}</p>
    {template && <><details><summary>Exact owner-selected contract and bounds</summary><pre>{JSON.stringify({contract_template:template.contract_template,limits:template.limits},null,2)}</pre></details>
      <p>Template digest <code>{template.template_sha256}</code>. Only the new goal ID varies; capabilities, budgets and required checks stay fixed.</p></>}
    <form onSubmit={submit}><label htmlFor="research-question">PUBLIC research question</label>
      <textarea id="research-question" rows={5} value={question} onChange={e=>{setQuestion(e.target.value);setConfirmed(false);}}
        disabled={pending || uncertain || !!receipt} required autoComplete="off" spellCheck={false} maxLength={4096}/>
      <p className="muted">{new TextEncoder().encode(question).length} / 4096 UTF-8 bytes. The confirmed PUBLIC question is retained in the selected private store.</p>
      <label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)} disabled={pending || uncertain || !!receipt}/>
        I reviewed the contract/bounds and confirm this question is PUBLIC. Do not execute it.</label>
      <div className="actions"><button disabled={!template || !csrf || pending || uncertain || !!receipt || !confirmed || !question.trim() || new TextEncoder().encode(question).length>4096}>Stage PUBLIC question</button>
        {receipt && <button type="button" disabled={pending} onClick={()=>{setReceipt(null);setGoal('');setLookup('');setQuestion('');setConfirmed(false);setNotice('Ready to review another PUBLIC question.');}}>New PUBLIC question</button>}</div>
    </form>
    {goal && <p>Goal ID <code data-testid="research-goal">{goal}</code></p>}
    <form onSubmit={inspect}><label htmlFor="research-lookup">Recover staged question by goal ID</label><div className="actions">
      <input id="research-lookup" className="receipt-id" value={lookup} onChange={e=>setLookup(e.target.value)} disabled={pending || uncertain} autoComplete="off" spellCheck={false}/>
      <button disabled={pending || !(uncertain?goal:lookup).trim()}>Inspect staged question</button></div></form>
    {receipt && <div aria-label="Staged question"><p>Operation <strong>STAGED_NO_EXECUTION</strong> · semantic support NOT_ASSESSED · execution authority NONE</p>
      <p>Canonical goal <strong data-testid="research-goal-state">{receipt.goal_status}</strong> · task <strong data-testid="research-task-state">{receipt.task_state}</strong></p>
      <p>Request <code>{receipt.request_id}</code> · task <code>{receipt.task_id}</code> · request hash <code>{receipt.request_sha256}</code></p>
      <h3>Retained PUBLIC question</h3><pre data-testid="research-question-text">{receipt.question}</pre><h3>Stored bounds</h3><pre>{JSON.stringify(receipt.limits,null,2)}</pre></div>}
  </section>;
}
