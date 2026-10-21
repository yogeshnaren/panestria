import {useEffect,useState} from 'react';
import type {components} from './schema';
import {Denied,json} from './client';
type Evidence = components['schemas']['BuildObservation'];
export function BuildEvidence({goal,owner,project,deny}:{goal:string,owner:string,project:string,deny:()=>void}) {
  const [open,setOpen] = useState(false);
  const [view,setView] = useState<Evidence|null>(null);
  const [fresh,setFresh] = useState(false);
  const [notice,setNotice] = useState('');
  useEffect(()=> {
    setOpen(false);setView(null);setFresh(false);setNotice('');
  },[goal]);
  useEffect(()=> {
    if (!open) return;
    const stop = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function read() {
      try {
        const page = await json<Evidence>(`/v1/activity/goals/${goal}/build-progress`,stop.signal);
        if(stop.signal.aborted) return;
        if(page.goal_id!==goal || page.owner_id!==owner || page.project_id!==project ||
          page.view_authority!=='READ_ONLY_PUBLIC_BUILD_EVIDENCE_METADATA' || page.dispatch_authority!=='NONE' ||
          page.release_acceptance!=='NOT_ASSESSED' || !Array.isArray(page.checks) || !Array.isArray(page.milestones) ||
          !Number.isSafeInteger(page.required_checks_total) || !Number.isSafeInteger(page.required_checks_passed) ||
          page.required_checks_passed<0 || page.required_checks_total<page.required_checks_passed)
          throw new Error('Unconfirmed progress.');
        setView(page);setFresh(true);setNotice('Protected evidence rechecked.');
      } catch(error) {
        if(stop.signal.aborted) return;
        setFresh(false);setView(null);
        setNotice('Build progress unconfirmed or not configured. The server needs an explicitly selected existing evidence store.');
        if(error instanceof Denied) {deny();return;}
      }
      if(!stop.signal.aborted) timer=setTimeout(()=>void read(),10000);
    }
    void read();
    return ()=>{stop.abort();clearTimeout(timer);};
  },[goal,owner,project,open]);
  return <section aria-label="Verified Build progress"><h2>Verified Build progress</h2>
    <p>Separate from activity, owner merge and release acceptance. PUBLIC plans only.</p>
    <button onClick={()=>setOpen(!open)}>{open?'Hide Build evidence':'Inspect Build evidence'}</button>
    {open && <><p role="status">{fresh?'Confirmed':'UNCONFIRMED'} · {notice}</p>
      {view && <><label htmlFor="build-checks">Final required checks: {view.required_checks_passed}/{view.required_checks_total}</label>
        <progress id="build-checks" value={view.required_checks_passed} max={Math.max(1,view.required_checks_total)}/>
        <p>Goal {view.goal_status} · owner merge {view.owner_merge} · release acceptance {view.release_acceptance}</p>
        <p>{view.attention_reason} · next: {view.next_action}</p>
        <p>Held claims {view.held_claims} · unknown invocations {view.unknown_invocations}</p>
        <p className="muted">Observed {view.observed_at} · event cursor {view.as_of_event_seq}</p>
        <ul>{view.checks.map(check=><li key={check.key}>{check.key}: <strong>{check.verdict}</strong> · {check.required?'required':'optional'}
          {check.report_sha256 && <><br/>Report <code>{check.report_sha256}</code></>}</li>)}</ul>
        <h3>Current plan milestones</h3><ul>{view.milestones.map(m=><li key={m.task_id}><code>{m.task_id}</code> · {m.state} · {m.evidence_status}
          {m.candidate_commit && <><br/>Candidate <code>{m.candidate_commit}</code></>}
          {m.evidence_sha256 && <><br/>Evidence <code>{m.evidence_sha256}</code></>}</li>)}</ul>
        <p>Contract <code>{view.contract_sha256}</code></p>
        <p>Final evidence <code>{view.final_evidence_sha256 ?? 'not confirmed'}</code></p>
      </>}
    </>}
  </section>;
}
