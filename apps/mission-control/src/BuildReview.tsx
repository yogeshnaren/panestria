import {useEffect,useRef,useState, type FormEvent} from 'react';
import type {components, operations} from './schema';
import {Denied,json} from './client';
type Review = components['schemas']['BuildReview'];
type Receipt = components['schemas']['BuildReviewReceipt'];
type Decision = operations['decide_review_v1_mission_goals__goal_id__build_review_decision_post']['requestBody']['content']['application/json'];
export function BuildReview({goal,owner,project,csrf,deny}:{goal:string,owner:string,project:string,csrf:string|null,deny:()=>void}) {
  const [open,setOpen]=useState(false), [view,setView]=useState<Review|null>(null);
  const [digest,setDigest]=useState(''), [confirm,setConfirm]=useState(false), [busy,setBusy]=useState(false);
  const [notice,setNotice]=useState(''), [at,setAt]=useState(0), [now,setNow]=useState(Date.now());
  const [revision,setRevision]=useState(0);
  const identity=useRef('');
  const lifetime=useRef<AbortController|null>(null);
  useEffect(()=>{const c=new AbortController();lifetime.current=c;return()=>c.abort();},[goal]);
  useEffect(()=>{if(!open)return;const t=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(t);},[open]);
  useEffect(()=> {
    if(!open || busy)return;
    const stop=new AbortController();let timer:ReturnType<typeof setTimeout>;
    async function read() {
      try {
        const page=await json<Review>(`/v1/mission/goals/${goal}/build-review`,stop.signal);
        if(stop.signal.aborted)return;
        if(page.goal_id!==goal || page.owner_id!==owner || page.project_id!==project ||
          page.dispatch_authority!=='NONE' || page.release_acceptance!=='NOT_ASSESSED' ||
          !/^[0-9a-f]{64}$/.test(page.effect_digest) || !/^[0-9a-f]{64}$/.test(page.review_sha256) ||
          !Number.isSafeInteger(page.expected_version) || !Array.isArray(page.checks) || typeof page.diff!=='string')
          throw new Error('Unconfirmed review.');
        const key=`${page.approval_id}:${page.review_sha256}:${page.expected_version}:${page.approval_state}`;
        if(identity.current!==key){setDigest('');setConfirm(false);identity.current=key;}
        setView(page);setAt(Date.now());setNotice('Exact protected preview rechecked. Consent records do not execute a merge.');
      } catch(error) {
        if(stop.signal.aborted)return;
        setView(null);setDigest('');setConfirm(false);
        setNotice('Review UNCONFIRMED. Protected content unavailable or changed; no decision submitted.');
        if(error instanceof Denied){deny();return;}
      }
      if(!stop.signal.aborted)timer=setTimeout(()=>void read(),10000);
    }
    void read();return()=>{stop.abort();clearTimeout(timer);};
  },[goal,owner,project,open,revision,busy]);
  const fresh=Boolean(view) && now-at<15000;
  const canDecide=fresh && view?.decision_available && csrf && digest===view.effect_digest && confirm && !busy;
  async function decide(event:FormEvent,decision:'approve'|'deny') {
    event.preventDefault();if(!canDecide || !view || !csrf || busy)return;
    setBusy(true);setConfirm(false);
    try {
      const body:Decision={
        approval_id:view.approval_id,effect_digest:view.effect_digest,expected_version:view.expected_version,
        review_sha256:view.review_sha256,decision,idempotency_key:crypto.randomUUID()
      };
      const receipt=await json<Receipt>(`/v1/mission/goals/${goal}/build-review/decision`,lifetime.current!.signal,body,csrf);
      if(lifetime.current!.signal.aborted)return;
      if(receipt.approval_id!==view.approval_id || receipt.effect_digest!==view.effect_digest ||
        receipt.state!==(decision==='approve'?'APPROVED':'DENIED') || receipt.dispatch_authority!=='NONE')
        throw new Error('Unconfirmed decision.');
      setNotice(`Consent ${receipt.state}. No merge dispatched. Inspect canonical state; continue through the existing owner Build CLI.`);
      setView(null);setOpen(false);
    } catch(error) {
      if(lifetime.current!.signal.aborted)return;
      setView(null);setOpen(false);
      setNotice('Decision UNCONFIRMED. Inspect canonical approval state before any further action. No automatic retry.');
      if(error instanceof Denied)deny();
    } finally {if(!lifetime.current!.signal.aborted){setBusy(false);setDigest('');}}
  }
  return <section aria-label="Exact Build review"><h2>Exact Build review and consent</h2>
    <p>PUBLIC protected diff and check reports are untrusted text. Recording consent does not dispatch, merge or accept a release.</p>
    <button disabled={busy} onClick={()=>{setOpen(!open);setView(null);setDigest('');setConfirm(false);}}>{open?'Close exact review':'Review exact merge request'}</button>
    <p role="status">{notice}</p>
    {open && <><button disabled={busy} onClick={()=>setRevision(revision+1)}>Refresh exact review</button>
      {!fresh && <p>STALE / UNCONFIRMED. Decisions disabled.</p>}
      {view && fresh && <>
        <p>Goal {view.goal_status} · task {view.task_state} · approval <strong>{view.approval_state}</strong> · version {view.expected_version}</p>
        <p>Release acceptance {view.release_acceptance} · dispatch {view.dispatch_authority}</p>
        <p>Effect digest <code data-testid="review-effect-digest">{view.effect_digest}</code></p>
        <p>Review hash <code>{view.review_sha256}</code></p>
        <pre aria-label="Canonical merge preview">{JSON.stringify(view.preview,null,2)}</pre>
        <p>Base <code>{view.base_commit}</code> · candidate <code>{view.candidate_commit}</code> · tree <code>{view.candidate_tree}</code></p>
        <h3>Exact protected diff</h3><pre aria-label="Protected diff">{view.diff}</pre>
        <h3>Independent check reports</h3>{view.checks.map(item=><details key={item.check.check_id}>
          <summary>{item.check.check_key}: {item.check.verdict} · {item.check.required?'required':'optional'}</summary>
          <p>Report <code>{item.check.report_sha256}</code></p><pre>{item.report}</pre>
        </details>)}
        {!csrf && <p>Pair again to enable the memory-only CSRF-protected consent controls.</p>}
        <form onSubmit={e=>void decide(e,'approve')}>
          <label htmlFor="review-digest">Type the exact effect digest to confirm this preview</label>
          <input id="review-digest" value={digest} onChange={e=>setDigest(e.target.value)} maxLength={64} autoComplete="off" spellCheck={false} disabled={busy}/>
          <label><input type="checkbox" checked={confirm} onChange={e=>setConfirm(e.target.checked)} disabled={busy}/>
            I reviewed this exact diff, checks and destination. This records consent only.</label>
          <div className="actions"><button disabled={!canDecide}>Record approval</button>
            <button type="button" disabled={!canDecide} onClick={e=>void decide(e,'deny')}>Record denial</button></div>
        </form>
      </>}
    </>}
  </section>;
}
