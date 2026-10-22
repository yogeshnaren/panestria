import {useEffect,useRef,useState,type FormEvent} from 'react';
import {Denied,json} from './client';
import type {components,operations} from './schema';
type View=components['schemas']['PlanRunView'];
type Intent=operations['start_run_v1_mission_build_plans__plan_id__run_post']['requestBody']['content']['application/json'];
type Cancellation=operations['cancel_run_v1_mission_build_plans__plan_id__run_cancel_post']['requestBody']['content']['application/json'];

export function PlanRun({owner,project,plan,sha,csrf,deny}:{owner:string,project:string,plan:string,sha:string,csrf:string|null,deny:()=>void}) {
  const [view,setView]=useState<View|null>(null),[notice,setNotice]=useState('Reading the canonical run request…');
  const [startAck,setStartAck]=useState(false),[cancelAck,setCancelAck]=useState(false),[pending,setPending]=useState(false);
  const [fresh,setFresh]=useState(false),[now,setNow]=useState(Date.now()),[at,setAt]=useState(0);
  const intent=useRef<Intent|null>(null),busy=useRef(false),controller=useRef(new AbortController()),denyRef=useRef(deny);denyRef.current=deny;
  const path=`/v1/mission/build/plans/${plan}/run`;
  function validate(value:View) {
    if(value.owner_id!==owner || value.project_id!==project || value.plan_id!==plan || value.plan_sha256!==sha ||
       value.merge_authority!=='NONE' || value.claim_release_authority!=='NONE' || value.release_acceptance!=='NOT_ASSESSED' ||
       !['NOT_REQUESTED','REQUESTED','CLAIMED_UNCONFIRMED','RETURN_RECORDED'].includes(value.state) ||
       (value.record && (value.record.plan_id!==plan || value.record.intent.plan_sha256!==sha)))throw new Error('Unconfirmed run');
    return value;
  }
  function retain(value:View) {
    if(value.record)intent.current=value.record.intent;
    setView(value);setFresh(true);setAt(Date.now());
  }
  async function inspect() {
    if(busy.current)return;
    try{const value=validate(await json<View>(path,controller.current.signal));if(controller.current.signal.aborted)return;
      retain(value);setNotice('Canonical request observed. Controller return and goal completion are separate facts.');
    }catch(error){if(controller.current.signal.aborted)return;setFresh(false);setView(null);
      if(error instanceof Denied)denyRef.current();else setNotice('DISCONNECTED / UNCONFIRMED. The original request is retained. No automatic POST was sent.');}
  }
  useEffect(()=>{const current=controller.current;void inspect();const poll=setInterval(()=>void inspect(),2000),clock=setInterval(()=>setNow(Date.now()),1000);
    return()=>{current.abort();clearInterval(poll);clearInterval(clock);};},[owner,project,plan,sha]);
  async function mutate(event:FormEvent,cancel:boolean) {
    event.preventDefault();if(!csrf || busy.current || !view || !fresh || now-at>=15000 || (cancel?!cancelAck:!startAck))return;
    if(cancel && !view.record)return;
    if(!cancel && !(['NOT_REQUESTED','REQUESTED'].includes(view.state)) )return;
    busy.current=true;setPending(true);setFresh(false);setStartAck(false);setCancelAck(false);
    if(!cancel && !intent.current)intent.current={request_id:crypto.randomUUID(),plan_sha256:sha,public_subscription_run:true};
    const body:Intent|Cancellation=cancel?{request_id:view.record!.intent.request_id,plan_sha256:sha,cancel_plan:true}:intent.current!;
    setNotice(cancel?'Withdrawing this plan’s authority. Unknown physical claims stay held.':'Recording one finite PUBLIC subscription run. Current native admission still applies.');
    try{const value=validate(await json<View>(path+(cancel?'/cancel':''),controller.current.signal,body,csrf));
      if(controller.current.signal.aborted)return;retain(value);setNotice(cancel?'Canonical cancellation inspected. Check goal/tasks and held claims below.':'Run request inspected. No automatic resume or final merge is enabled.');
    }catch(error){if(controller.current.signal.aborted)return;setView(null);
      if(error instanceof Denied)denyRef.current();else setNotice('UNCONFIRMED mutation. Inspect this same plan; no automatic POST retry was sent.');}
    finally{busy.current=false;setPending(false);}
  }
  const current=fresh && now-at<15000;
  const canStart=current && view?.configuration_current && !['CANCELLED','FAILED','COMPLETED'].includes(view?.goal_status??'') &&
    (view?.state==='NOT_REQUESTED' || (view?.state==='REQUESTED' && !view.expired));
  return <section aria-label="Finite Build run"><h3>Run this accepted plan</h3>
    <p>One explicitly requested foreground run, using the configured Claude subscription and up to two workers. Current policy, runtime qualification, exact inventory, capacity, storage and task admission are checked before dispatch. No API fallback or automatic merge.</p>
    <p role="status" data-testid="plan-run-notice">{notice}</p>
    <button type="button" disabled={pending} onClick={()=>void inspect()}>Inspect run request</button>
    {intent.current && <p>Original request <code data-testid="plan-run-request">{intent.current.request_id}</code></p>}
    {view && current && <><p>Request <strong data-testid="plan-run-state">{view.state}</strong> · goal <strong>{view.goal_status}</strong> · local controller {view.controller_active?'active':'not observed active'}.</p>
      {view.record && <p>Start-admission deadline <code>{view.record.expires_at}</code>{view.expired?' · expired; existing work is not released by expiry':''}.</p>}
      {view.result && <p>Controller {view.result.outcome} · runner status <strong data-testid="plan-run-result">{view.result.runner_status}</strong>. A controller return grants no task PASS, physical claim release or merge.</p>}
      {view.storage && <div role="status"><strong>Storage {view.storage.decision}</strong> · {view.storage.reason}
        <p>Available bytes: {view.storage.available_bytes??'unknown'} · anticipated write bytes: {view.storage.anticipated_write_bytes??'unknown'} (owner estimate, not a write cap).</p>
        {view.storage.warnings.length>0 && <p>Warnings: {view.storage.warnings.join(', ')}. Review storage inspect recommendations before more work. Cleanup authority NONE.</p>}
      </div>}
      {!view.configuration_current && <p>Configuration differs from this request. Inspect the original operator setup; another run is blocked.</p>}
      <form onSubmit={event=>void mutate(event,false)}><label><input type="checkbox" checked={startAck} onChange={e=>setStartAck(e.target.checked)} disabled={!canStart || pending}/>
        I reviewed this exact accepted PUBLIC plan and authorize one bounded Claude subscription run now, with zero API cash and no paid fallback. Keep final merge separate.</label>
        <button disabled={!csrf || !canStart || !startAck || pending}>{view.state==='REQUESTED'?'Start recorded request':'Start finite Build run'}</button></form>
      {view.record && !['CANCELLED','COMPLETED','FAILED'].includes(view.goal_status) && <form onSubmit={event=>void mutate(event,true)}>
        <label><input type="checkbox" checked={cancelAck} onChange={e=>setCancelAck(e.target.checked)} disabled={pending}/>Cancel this entire plan and withdraw new work. Uncertain physical claims remain held.</label>
        <button disabled={!csrf || !cancelAck || pending}>Cancel this Build plan</button></form>}
      <p className="muted">A claimed request without a recorded return is unconfirmed. Restart, lease expiry, logout and a new request ID cannot rerun it. Use canonical task/evidence inspection and the existing operator reconciliation workflow.</p>
    </>}
  </section>;
}
