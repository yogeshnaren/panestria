import {useEffect,useState} from 'react';
import {Denied,json} from './client';
import type {components} from './schema';

type Status=components['schemas']['StorageStatus'];
const count=(v:unknown)=>v===null || (typeof v==='number' && Number.isSafeInteger(v) && v>=0);
const bytes=(v:number|null|undefined)=>typeof v==='number' && Number.isSafeInteger(v) && v>=0 ? `${(v/1073741824).toFixed(2)} GiB`:'UNKNOWN';
function valid(s:Status,owner:string,project:string) {
  if(s.owner_id!==owner || s.project_id!==project || s.scope!=='OWNER_HOST_METADATA_NOT_PROJECT_ATTRIBUTION' ||
     s.source!=='UNPRIVILEGED_LOCAL_READ_ONLY' || s.cleanup_authority!=='NONE' || s.acceptance_authority!=='NONE' ||
     s.qualification!=='NOT_ASSESSED' || !['NOT_CONFIGURED','DISABLED','COLLECTING','OBSERVED','UNAVAILABLE','STALLED'].includes(s.state) ||
     typeof s.next_check_seconds!=='number' || !Number.isSafeInteger(s.next_check_seconds) || s.next_check_seconds<1 ||
     typeof s.sample_interval_seconds!=='number' || !Number.isSafeInteger(s.sample_interval_seconds) || s.sample_interval_seconds<60 ||
     !Array.isArray(s.components) || s.components.length>12 || !Array.isArray(s.warnings) || s.warnings.length>32 ||
     !s.components.every(c=>/^[a-zA-Z0-9_-]{1,48}$/.test(c.label) && count(c.bytes) && ['OBSERVED','ESTIMATED','UNKNOWN'].includes(c.status)) ||
     !s.warnings.every(w=>['INFO','WARNING','CRITICAL'].includes(w.severity) && /^[a-zA-Z0-9_-]{1,80}$/.test(w.code) &&
       typeof w.recommendation==='string' && w.recommendation.length<=1024)) throw new Error('Unconfirmed host observation.');
  if(s.capacity && ![s.capacity.total_bytes,s.capacity.used_bytes,s.capacity.available_bytes,s.capacity.reserved_bytes].every(count))
    throw new Error('Unconfirmed storage capacity.');
  return s;
}
export function StorageNotices({owner,project,now,deny}:{owner:string,project:string,now:number,deny:()=>void}) {
  const [view,setView]=useState<Status|null>(null);
  const [notice,setNotice]=useState('Reading selected owner host metadata…');
  useEffect(()=>{
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
    async function read() {
      let delay=60000;
      try {
        const data=valid(await json<Status>('/v1/activity/storage',controller.signal),owner,project);
        if(controller.signal.aborted)return;
        setView(data);setNotice(`Storage ${data.state}: ${data.reason}`);
        delay=Math.min(60000,Math.max(1000,data.next_check_seconds*1000));
      } catch(error) {
        if(controller.signal.aborted)return;
        setView(null);setNotice('Storage UNCONFIRMED. Check the private settings or server; no cleanup is performed.');
        if(error instanceof Denied){deny();return;}
      }
      if(!controller.signal.aborted)timer=setTimeout(()=>void read(),delay);
    }
    void read();return()=>{controller.abort();clearTimeout(timer);};
  },[owner,project]);
  const stamp=view?.observed_at?Date.parse(view.observed_at):NaN;
  const fresh=!!view && Number.isFinite(stamp) && stamp<=now+5000 && now-stamp<=(view.sample_interval_seconds+35)*1000;
  const observed=view && fresh && view.notifications_enabled===true && ['OBSERVED','COLLECTING'].includes(view.state);
  return <section aria-label="Storage notices"><h2>Owner host storage notices</h2>
    <p role="status">{notice}{view?.observed_at && !fresh?' · STALE / UNCONFIRMED':''}</p>
    <p>Explicitly selected host metadata; these are not project ownership totals. Cleanup and acceptance authority: NONE.</p>
    {observed && <>
      <p>Observed {view.observed_at}. Used: {view.capacity?.status==='OBSERVED' && typeof view.capacity.used_percent==='number' && Number.isFinite(view.capacity.used_percent)?`${view.capacity.used_percent.toFixed(2)}%`:'UNKNOWN'} · owner available: {bytes(view.capacity?.available_bytes)} · reserved blocks: {bytes(view.capacity?.reserved_bytes)}.</p>
      {view.warnings.map(w=><div key={w.code} role={w.severity==='CRITICAL'?'alert':'status'}><strong>{w.severity} {w.code}</strong><p>{w.recommendation}</p></div>)}
      {view.components.length>0 && <><h3>Selected component estimates</h3><ul>{view.components.map(c=><li key={c.label}>{c.label}: {c.status==='UNKNOWN'?'UNKNOWN':bytes(c.bytes)} · {c.status} · {c.basis}{typeof c.filesystem_share_percent==='number' && Number.isFinite(c.filesystem_share_percent)?` · estimated filesystem share ${c.filesystem_share_percent.toFixed(2)}%`:''}</li>)}</ul>
        <p>Logical/shared estimates may overlap; do not add them as exclusive physical totals. Reclaimable does not mean safe to delete.</p></>}
      {view.timeshift_status!=='NOT_REQUESTED' && <><h3>Timeshift schedule observation</h3><p>{view.timeshift_status}; physical snapshot bytes UNKNOWN.</p>
        {view.timeshift_schedules && <ul>{(['hourly','daily','weekly','monthly','boot'] as const).map(k=><li key={k}>{k}: {view.timeshift_schedules?.[k]===true?'enabled':view.timeshift_schedules?.[k]===false?'disabled':'UNKNOWN'}</li>)}</ul>}</>}
    </>}
    <p>No deletion, pruning, volume removal or backup-setting change is available here. Review recommendations and ownership/dependencies as the owner before deciding on storage changes.</p>
  </section>;
}
