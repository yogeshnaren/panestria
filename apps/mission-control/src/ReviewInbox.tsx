import {useEffect,useRef,useState} from 'react';
import {Denied,json} from './client';
import type {components} from './schema';
type Inbox=components['schemas']['ReviewInbox'];
export function ReviewInbox({owner,project,now,canInspectPlan,onPlan,onGoal,deny}:{owner:string,project:string,now:number,canInspectPlan:boolean,onPlan:(id:string)=>void,onGoal:(id:string)=>void,deny:()=>void}) {
  const [view,setView]=useState<Inbox|null>(null),[after,setAfter]=useState<string|null>(null),[version,setVersion]=useState(0),[at,setAt]=useState(0);
  const [notice,setNotice]=useState('Reading canonical pending reviews…');const denyRef=useRef(deny);denyRef.current=deny;
  useEffect(()=>{const controller=new AbortController();setView(null);setAt(0);
    const read=async()=>{try{const value=await json<Inbox>(`/v1/activity/reviews?limit=16${after?`&after=${after}`:''}`,controller.signal);
      if(value.owner_id!==owner || value.project_id!==project || value.view_authority!=='READ_ONLY_METADATA' || value.decision_authority!=='NONE' || !Array.isArray(value.entries) || value.entries.length>16)throw new Error('Unconfirmed inbox');
      if(controller.signal.aborted)return;setView(value);setAt(performance.now());setNotice('Canonical pending records observed. Exact current review is required before any decision.');
    }catch(error){if(controller.signal.aborted)return;setView(null);setAt(0);if(error instanceof Denied)denyRef.current();else setNotice('Pending reviews UNCONFIRMED. Entries hidden; retry or return to first page.');}};
    void read();const timer=setInterval(()=>void read(),10000);return()=>{controller.abort();clearInterval(timer);};
  },[owner,project,after,version]);
  const fresh=!!view && now-at<15000;
  return <section aria-label="Pending review inbox"><h2>Pending reviews</h2><p role="status" data-testid="inbox-notice">{notice}{view && !fresh?' STALE / UNCONFIRMED.':''}</p>
    <p className="muted">Latest unaccepted plans and pending action approvals for open goals. Oldest expiry first, including expired records. Metadata is not a qualified preview, decision or execution permission.</p>
    {fresh && view && <><p>Observed {view.observed_at} · read-only metadata · decision authority NONE</p>
      {!view.entries.length && <p>No pending reviews in this page.</p>}
      <div className="scroll"><table><thead><tr><th>Review</th><th>Canonical state</th><th>Expiry</th><th>Inspect</th></tr></thead><tbody>
        {view.entries.map(entry=><tr key={`${entry.kind}:${entry.id}`} data-review-id={entry.id}>
          <td>{entry.kind==='PLAN'?'Plan consent':'Action approval'}<br/><code>{entry.id}</code><br/>Goal <code>{entry.goal_id}</code></td>
          <td>{entry.canonical_state}<br/>Goal {entry.goal_status}</td><td>{entry.expires_at}<br/>{entry.expired?'EXPIRED · inspect before deciding':'Expiry not yet reached; other guards still apply'}</td>
          <td>{entry.kind==='PLAN'?(canInspectPlan?<button onClick={()=>onPlan(entry.id)}>Select plan for inspection</button>:<span>Review this plan on the workstation using its ID.</span>):<button onClick={()=>onGoal(entry.goal_id)}>Open approval goal</button>}</td>
        </tr>)}
      </tbody></table></div></>}
    <div className="actions"><button onClick={()=>{setAfter(null);setVersion(v=>v+1);}}>First page / refresh reviews</button>
      <button disabled={!fresh || !view?.next_cursor} onClick={()=>setAfter(view?.next_cursor ?? null)}>More pending reviews</button></div>
  </section>;
}
