import { Component, useEffect, useState, type ReactNode, type FormEvent } from 'react';
import { createRoot } from 'react-dom/client';
import { Denied, json, mergeEvents, validateTimeline, waitForChange, type Activity, type Timeline, type Event, type Scope } from './client';
import './style.css';
import {BuildEvidence} from './BuildEvidence';
import {BuildReview} from './BuildReview';
import {OfflineAsk} from './OfflineAsk';
import {ResearchIntake} from './ResearchIntake';
import {BuildIntake} from './BuildIntake';
import {ReviewInbox} from './ReviewInbox';
import {StorageNotices} from './StorageNotices';
// Fixed server mode label; authenticated capabilities must independently agree.
const root = document.getElementById('root')?.dataset;
const phoneMode = root?.phoneObserver === 'true';
// The owner app (panestria serve) names its session scopes, each paired separately.
const SCOPES: Scope[] = ['activity','ask','build'];
const ownerScopes = (root?.sessionScopes ?? '').split(' ').filter(Boolean) as Scope[];
const owner = ownerScopes.length > 0;
const ownerModeValid = ownerScopes.every((scope,i) => SCOPES.includes(scope) && ownerScopes.indexOf(scope) === i) &&
  (!owner || (!phoneMode && ownerScopes.includes('ask')));
const scopeName: Record<Scope,string> = {activity:'Activity', ask:'Ask', build:'Build'};
const scopeReach: Record<Scope,string> = {
  activity:'Observes project activity and Build progress only.',
  ask:'Asks offline questions and reads their receipts.',
  build:'Reads Build diffs, records decisions, accepts plans and starts runs.'};
type Paired = {csrf:string, expires:number};
// The page and the authenticated capabilities name different scopes or features.
class OwnerModeMismatch extends Error {}

function useGoal(goal: string | null, scope: Activity | null, denied: () => void) {
  const [view, setView] = useState<{page: Timeline | null, events: Event[], notice: string, fresh: boolean, observedAt: number}>(
    {page:null,events:[],notice:'Select a goal.',fresh:false,observedAt:0});
  useEffect(() => {
    const controller = new AbortController();
    setView({page:null,events:[],notice:'Reading canonical state…',fresh:false,observedAt:0});
    if (!goal || !scope) return () => controller.abort();
    const path = `/v1/activity/goals/${goal}/events`;
    let after = '0', backoff = 1000;
    void (async () => {
      while (!controller.signal.aborted) {
        try {
          const page = validateTimeline(await json<Timeline>(`${path}?after=${after}`, controller.signal), goal, scope);
          if (controller.signal.aborted) return;
          setView(prior => ({page,events:mergeEvents(prior.events,page),fresh:true,observedAt:performance.now(),
            notice:page.resync ? 'History resynchronized. Older retained events are unavailable.' : 'Canonical snapshot confirmed.'}));
          const previous = after; after = page.next_cursor; backoff = 1000;
          if (!page.resync && page.events.length === 50 && after !== previous) continue;
          await waitForChange(path, after, controller.signal);
        } catch (error) {
          if (controller.signal.aborted) return;
          if (error instanceof Denied) { setView({page:null,events:[],notice:'Access ended. Pair again.',fresh:false,observedAt:0}); denied(); return; }
          setView(prior => ({...prior, fresh:false, notice:'Disconnected / unconfirmed. Reconnecting with canonical backfill…'}));
          await new Promise<void>(resolve => {
            const timer = setTimeout(resolve, backoff);
            controller.signal.addEventListener('abort', () => {clearTimeout(timer); resolve();}, {once:true});
          });
          backoff = Math.min(backoff * 2, 10000);
        }
      }
    })();
    return () => controller.abort();
  }, [goal, scope?.owner_id, scope?.project_id]);
  return view;
}
function Dashboard() {
  if (!ownerModeValid) throw new Error('Unconfirmed owner mode.');
  const [now,setNow] = useState(Date.now());
  const [monotonicNow,setMonotonicNow] = useState(performance.now());
  const [readEpoch,setReadEpoch] = useState(0);
  const [listAt,setListAt] = useState(0);
  const [lastObserved,setLastObserved] = useState<string|null>(null);
  useEffect(() => {const timer = setInterval(()=>{setNow(Date.now());setMonotonicNow(performance.now());},1000);return ()=>clearInterval(timer);},[]);
  const [activity,setActivity] = useState<Activity|null>(null);
  const [goal,setGoal] = useState<string|null>(null);
  const [notice,setNotice] = useState('Pair to inspect this project.');
  const [code,setCode] = useState('');
  const [csrf,setCsrf] = useState<string|null>(null);
  const [mayRead,setMayRead] = useState(true);
  const [authenticated,setAuthenticated] = useState(false);
  const [busy,setBusy] = useState(false);
  const [before,setBefore] = useState<string|null>(null);
  const [listFresh,setListFresh] = useState(false);
  const [reviewMode,setReviewMode] = useState(false);
  const [askMode,setAskMode] = useState(false);
  const [researchMode,setResearchMode] = useState(false);
  const [buildIntakeMode,setBuildIntakeMode] = useState(false);
  const [planAcceptanceMode,setPlanAcceptanceMode] = useState(false);
  const [buildRunMode,setBuildRunMode] = useState(false);
  const [storageMode,setStorageMode] = useState(false);
  const [planSelection,setPlanSelection]=useState<{id:string,version:number}|null>(null);
  // Owner app: one memory-only CSRF token and expiry per scope paired in this tab.
  const [sessions,setSessions] = useState<Partial<Record<Scope,Paired>>>({});
  const [codes,setCodes] = useState<Partial<Record<Scope,string>>>({});
  const [scopeNotice,setScopeNotice] = useState<Partial<Record<Scope,string>>>({});
  const denied = (_reason?: Denied) => {setMayRead(false); setAuthenticated(false); setActivity(null); setGoal(null); setCsrf(null); setSessions({}); setListFresh(false);setPlanSelection(null);setLastObserved(null);};
  const live = (scope: Scope) => {const session = sessions[scope]; return session && session.expires > now ? session : undefined;};
  const csrfFor = (scope: Scope) => owner ? live(scope)?.csrf ?? null : csrf;
  // A refusal on an Ask or Build route ends only that scope here; the other
  // scopes stay paired. Activity reads accept every scope, so their refusal ends all.
  const lost = (scope: Scope) => (reason: Denied) => {
    setScopeNotice(prior => ({...prior, [scope]: reason.code === 'session_scope_denied'
      ? `${scopeName[scope]} session required. Pair ${scopeName[scope]} to continue; other sessions are unchanged.`
      : `${scopeName[scope]} session ended or was refused. Pair ${scopeName[scope]} again; other sessions are unchanged.`}));
    if (!sessions[scope]) return;
    setSessions(prior => {const next = {...prior}; delete next[scope]; return next;});
    setReadEpoch(value => value + 1);  // Confirm at once whether another session still reads activity.
  };
  const denyFor = (scope: Scope) => owner ? lost(scope) : denied;
  const timeline = useGoal(goal, activity, denied);
  useEffect(()=>{
    if(!phoneMode)return;
    const reset=()=>{setActivity(null);setListFresh(false);setReadEpoch(value=>value+1);
      setNotice(document.visibilityState==='hidden'?'View paused in the background.':!navigator.onLine?'This device is offline. Workstation state is unconfirmed.':'Rechecking current workstation state…');};
    document.addEventListener('visibilitychange',reset);
    window.addEventListener('pageshow',reset);window.addEventListener('online',reset);window.addEventListener('offline',reset);
    return()=>{document.removeEventListener('visibilitychange',reset);window.removeEventListener('pageshow',reset);window.removeEventListener('online',reset);window.removeEventListener('offline',reset);};
  },[]);
  async function load(cursor: string|null, signal: AbortSignal) {
    const data = await json<Activity>(`/v1/activity?limit=16${cursor ? `&before=${cursor}` : ''}`,AbortSignal.any([signal,AbortSignal.timeout(5000)]));
    if (data.view_authority !== 'READ_ONLY_METADATA' || data.acceptance_authority !== 'NONE' ||
        !Array.isArray(data.entries) || data.entries.length > 16 || typeof data.observed_at!=='string' ||
        !Number.isFinite(Date.parse(data.observed_at))) throw new Error('Unconfirmed project response.');
    if (signal.aborted) return;
    const capabilities = await json<{build_review_enabled:boolean,offline_ask_enabled:boolean,research_intake_enabled:boolean,build_intake_enabled:boolean,plan_acceptance_enabled:boolean,build_run_enabled:boolean,storage_status_enabled?:boolean,private_phone_enabled?:boolean,dispatch_authority:string,session_scopes?:Scope[]}>('/v1/mission/capabilities',signal);
    if (signal.aborted) return;
    const build = ownerScopes.includes('build');
    if((capabilities.session_scopes ?? []).join(' ')!==ownerScopes.join(' ') || (owner &&
      (!capabilities.offline_ask_enabled || capabilities.research_intake_enabled || capabilities.storage_status_enabled ||
       [capabilities.build_review_enabled,capabilities.build_intake_enabled,capabilities.plan_acceptance_enabled,capabilities.build_run_enabled].some(value=>value!==build))))
      throw new OwnerModeMismatch('Unconfirmed owner mode.');
    if(typeof capabilities.build_review_enabled!=='boolean' || typeof capabilities.offline_ask_enabled!=='boolean' || typeof capabilities.research_intake_enabled!=='boolean' || typeof capabilities.build_intake_enabled!=='boolean' || typeof capabilities.plan_acceptance_enabled!=='boolean' || typeof capabilities.build_run_enabled!=='boolean' || capabilities.dispatch_authority!==(capabilities.build_run_enabled?'EXPLICIT_FOREGROUND_BUILD':'NONE')) throw new Error('Unconfirmed mode.');
    if(capabilities.storage_status_enabled!==undefined && typeof capabilities.storage_status_enabled!=='boolean') throw new Error('Unconfirmed host-data mode.');
    if((capabilities.private_phone_enabled??false)!==phoneMode || (phoneMode &&
      (capabilities.build_review_enabled || capabilities.offline_ask_enabled || capabilities.research_intake_enabled ||
       capabilities.build_intake_enabled || capabilities.plan_acceptance_enabled || capabilities.build_run_enabled || capabilities.storage_status_enabled)))
      throw new Error('Unconfirmed phone observer mode.');
    if(capabilities.storage_status_enabled && (capabilities.build_review_enabled || capabilities.offline_ask_enabled || capabilities.research_intake_enabled || capabilities.build_intake_enabled || capabilities.plan_acceptance_enabled || capabilities.build_run_enabled)) throw new Error('Unconfirmed mode combination.');
    setStorageMode(capabilities.storage_status_enabled===true);
    setReviewMode(capabilities.build_review_enabled);
    setAskMode(capabilities.offline_ask_enabled);
    setResearchMode(capabilities.research_intake_enabled);
    setBuildIntakeMode(capabilities.build_intake_enabled);
    setPlanAcceptanceMode(capabilities.plan_acceptance_enabled);
    setBuildRunMode(capabilities.build_run_enabled);
    setMayRead(true); setActivity(data); setLastObserved(data.observed_at); setListAt(performance.now()); setListFresh(true); setAuthenticated(true); setNotice('Project snapshot confirmed.');
  }
  useEffect(() => {
    const controller = new AbortController();
    if (!mayRead || (phoneMode && (document.visibilityState==='hidden' || !navigator.onLine))) return () => controller.abort();
    // Cookie can survive a reload; CSRF stays memory-only, so logout requires
    // re-pairing after reload. Read-only metadata still authenticates normally.
    const read = async () => {try {await load(before,controller.signal);} catch (error) {
      if (controller.signal.aborted) return;
      if (error instanceof Denied) denied();
      setListFresh(false); setNotice(error instanceof OwnerModeMismatch
        ? 'This page and the server disagree on session scopes. Nothing new is shown; reload the page.'
        : 'Project unconfirmed. Pair or retry when the server is available.');
    }};
    void read(); const timer = setInterval(() => void read(),10000);
    return () => {controller.abort();clearInterval(timer);};
  },[before,mayRead,readEpoch]);
  async function pair(event: FormEvent) {
    event.preventDefault(); if (busy) return; setBusy(true);
    try {
      const data = await json<{csrf_token:string}>('/v1/session/pair',AbortSignal.timeout(5000),{code});
      setCode(''); setCsrf(data.csrf_token); setBefore(null);
      await load(null,AbortSignal.timeout(5000));
    } catch {setCode('');denied();setNotice('Pairing failed. Request a new one-use code in your terminal.');}
    finally {setBusy(false);}
  }
  async function pairScope(scope: Scope, event: FormEvent) {
    event.preventDefault(); if (busy) return; setBusy(true);
    const code = codes[scope] ?? ''; setCodes(prior => ({...prior, [scope]: ''}));
    try {
      const data = await json<{csrf_token:string,expires_at:string}>(`/v1/session/${scope}/pair`,AbortSignal.timeout(5000),{code});
      const expires = Date.parse(data.expires_at);
      if (typeof data.csrf_token !== 'string' || !data.csrf_token || !Number.isFinite(expires)) throw new Error('Unconfirmed pairing.');
      setSessions(prior => ({...prior, [scope]: {csrf:data.csrf_token, expires}}));
      setScopeNotice(prior => ({...prior, [scope]: `${scopeName[scope]} paired in this tab.`}));
    } catch {
      setScopeNotice(prior => ({...prior, [scope]: `Pairing failed. Run panestria pair-code --scope ${scope} for a new one-use code.`}));
      return;
    } finally {setBusy(false);}
    setBefore(null); setMayRead(true); setReadEpoch(value => value + 1);
  }
  async function logoutScope(scope: Scope) {
    const session = sessions[scope]; if (!session || busy) return; setBusy(true);
    try {
      await json(`/v1/session/${scope}/logout`,AbortSignal.timeout(5000),{},session.csrf);
      setSessions(prior => {const next = {...prior}; delete next[scope]; return next;});
      setScopeNotice(prior => ({...prior, [scope]: `${scopeName[scope]} session revoked.`}));
      setReadEpoch(value => value + 1);  // Confirm what the remaining sessions can still read.
    } catch {setScopeNotice(prior => ({...prior, [scope]: 'Logout unconfirmed. The server session may still be active; retry.'}));}
    finally {setBusy(false);}
  }
  async function logout() {
    if (!csrf || busy) return; setBusy(true);
    try { await json('/v1/session/logout',AbortSignal.timeout(5000),{},csrf); denied(); setNotice('Session revoked.'); }
    catch {setNotice('Logout unconfirmed. Server session may still be active; retry.');}
    finally {setBusy(false);}
  }
  return <main className={phoneMode?'phone-observer':undefined}>
    <header><p className="eyebrow">PANESTRIA · {owner?(ownerScopes.includes('build')?'OWNER · ASK AND BUILD':'OWNER · ASK'):phoneMode?'PRIVATE PHONE OBSERVER':storageMode?'OWNER HOST STORAGE':buildRunMode?'EXPLICIT PUBLIC BUILD':askMode?'OFFLINE ASK':researchMode?'PUBLIC DELEGATE STAGING':planAcceptanceMode?'PUBLIC PLAN REVIEW':buildIntakeMode?'PUBLIC BUILD PLAN STAGING':'LOCAL OBSERVER'}</p><h1>Mission Control</h1>
      <p>Canonical project activity and goal timelines. {owner?(ownerScopes.includes('build')?'Offline Ask, and explicit PUBLIC Build review, plan acceptance and finite runs, each behind its own paired session':'Offline Ask behind its own paired session'):buildRunMode?'Explicit PUBLIC plan review and finite subscription execution':askMode?'Explicit offline Ask input':researchMode?'Explicit PUBLIC question staging':planAcceptanceMode?'Explicit PUBLIC plan review and acceptance':buildIntakeMode?'Explicit PUBLIC Build plan staging':reviewMode?'Explicit PUBLIC Build review and consent records':'Read-only metadata'} · release acceptance authority: NONE.</p></header>
    <section aria-label="Connection"><p role="status">{notice}</p>
      {phoneMode && <p className="muted" data-testid="last-observed">Workstation last confirmed: {lastObserved??'not yet observed'}. This time describes the last successful read, not current availability.</p>}
      {phoneMode && <p className="muted">Swipe tables sideways to inspect all columns. Decisions and work stay on the workstation.</p>}
      {owner && <div className="scopes">{ownerScopes.map(scope => {
        const session = sessions[scope], current = live(scope);
        return <section key={scope} aria-label={`${scopeName[scope]} session`}><h2>{scopeName[scope]} session</h2>
          <p className="muted">{scopeReach[scope]}</p>
          <p data-testid={`session-${scope}`}>{current ? `Paired in this tab until ${new Date(current.expires).toLocaleTimeString()}.` : session ? 'Expired. Pair again.' : 'Not paired in this tab.'}</p>
          {scopeNotice[scope] && <p role="status" data-testid={`session-${scope}-notice`}>{scopeNotice[scope]}</p>}
          {current ? <button onClick={()=>void logoutScope(scope)} disabled={busy}>Log out of {scopeName[scope]}</button> :
            <form onSubmit={event=>void pairScope(scope,event)}><label htmlFor={`pair-${scope}`}>One-use {scopeName[scope]} code from <code>panestria pair-code --scope {scope}</code></label>
              <div className="actions"><input id={`pair-${scope}`} value={codes[scope] ?? ''} onChange={e=>{const value=e.target.value.toUpperCase();setCodes(prior=>({...prior,[scope]:value}));}}
                pattern="[0-9A-F]{8}" maxLength={8} minLength={8} required autoComplete="off" autoCapitalize="characters" spellCheck={false}/>
                <button disabled={busy}>Pair {scopeName[scope]}</button></div></form>}
        </section>;})}</div>}
      {!owner && (!authenticated || !csrf) && <form onSubmit={pair}><label htmlFor="pair">One-use pairing code from your terminal</label>
        <div className="actions"><input id="pair" value={code} onChange={e=>setCode(e.target.value.toUpperCase())}
          className={phoneMode?'phone-code':undefined} pattern={phoneMode?'[0-9A-F]{32}':'[0-9A-F]{8}'} maxLength={phoneMode?32:8} minLength={phoneMode?32:8} required autoComplete="off" autoCapitalize="characters" spellCheck={false}/>
          <button disabled={busy}>Pair</button></div></form>}
      {!owner && csrf && <button onClick={()=>void logout()} disabled={busy}>Log out</button>}
      <p className="muted">{askMode?'Enter questions only in Offline Ask below. Never enter credentials or bearer tokens.':researchMode?'Only explicitly PUBLIC questions belong in Delegate staging. Never enter credentials or private information.':buildIntakeMode?'Only explicitly PUBLIC zero-cash plan bundles belong here. Never include credentials or private information.':reviewMode?'Never enter credentials or private content. Protected PUBLIC evidence is displayed only below.':'No bearer token, private question, diff or source text belongs in this view.'}</p>
    </section>
    {authenticated && activity && <>
      {storageMode && <StorageNotices key={`storage:${activity.project_id}`} owner={activity.owner_id} project={activity.project_id} now={now} deny={denied}/>}
      {askMode && <OfflineAsk key={`ask:${activity.project_id}`} project={activity.project_id} csrf={csrfFor('ask')} deny={denyFor('ask')}/>}
      {researchMode && <ResearchIntake key={`research:${activity.project_id}`} owner={activity.owner_id} project={activity.project_id} csrf={csrf} deny={denied}/>}
      {buildIntakeMode && <BuildIntake key={`build-intake:${activity.project_id}`} owner={activity.owner_id} project={activity.project_id} csrf={csrfFor('build')} deny={denyFor('build')} allowAcceptance={planAcceptanceMode} allowRun={buildRunMode} selection={planSelection}/>}
      <ReviewInbox owner={activity.owner_id} project={activity.project_id} now={monotonicNow} canInspectPlan={buildIntakeMode} onPlan={id=>setPlanSelection(prior=>({id,version:(prior?.version??0)+1}))} onGoal={setGoal} deny={denied}/>
      <section aria-label="Project activity"><h2>Project activity</h2>
        <p data-testid="project-freshness">Project <code>{activity.project_id}</code> · {listFresh && monotonicNow-listAt < 15000 ? 'Confirmed' : 'STALE / UNCONFIRMED'}</p>
        <p className="muted">Observed {activity.observed_at}. Statuses are canonical observations, not release acceptance.</p>
        {!activity.entries.length && <p>No activity in this project yet.</p>}
        <div className="scroll"><table><thead><tr><th>Work</th><th>State</th><th>Tasks / reviews</th><th>Inspect</th></tr></thead><tbody>
          {activity.entries.map(entry=><tr key={`${entry.source}:${entry.id}`}><td>{entry.workflow}<br/><code>{entry.id}</code></td>
            <td>{entry.canonical_state}{entry.needs_attention ? ' · attention needed' : ''}</td>
            <td>{entry.active_tasks} / {entry.waiting_reviews}<br/>Held claims: {entry.held_build_claims ?? 'unknown'}</td>
            <td>{entry.source === 'GOAL' ? <button onClick={()=>setGoal(entry.id)}>Open goal {entry.id.slice(0,8)}</button> : 'Ask receipt; no goal timeline'}</td></tr>)}
        </tbody></table></div>
        <div className="actions"><button onClick={()=>{setBefore(null);setGoal(null);}} disabled={!before}>Latest</button>
          <button disabled={!activity.next_cursor} onClick={()=>{setBefore(activity.next_cursor ?? null);setGoal(null);}}>Older activity</button></div>
      </section>
      {goal && <section aria-label="Goal timeline"><h2>Goal timeline</h2><code>{goal}</code>
        <p role="status">{timeline.fresh && monotonicNow-timeline.observedAt < 15000 ? 'Confirmed' : 'STALE / UNCONFIRMED'} · {timeline.notice}</p>
        {timeline.page && <><p>Canonical goal: <strong data-testid="goal-state">{timeline.page.snapshot.status}</strong></p>
          <h3>Tasks</h3><ul>{timeline.page.snapshot.tasks.map(task=><li key={task.id}><code>{task.id}</code> · {task.state} · version {task.row_version} · epoch {task.lease_epoch}</li>)}</ul>
          <h3>Events</h3><p className="muted">Latest 200 observed metadata entries, oldest first. A resync drops unverifiable history. Event names never change the displayed canonical status.</p>
          <ol aria-label="Events">{timeline.events.map(event=><li key={event.id} data-event-id={event.id}><code>{event.seq}</code> · {event.kind} · {event.privacy_label}</li>)}</ol>
          <p>Replay cursor <code data-testid="cursor">{timeline.page.next_cursor}</code></p></>}
      </section>}
      {goal && reviewMode && <BuildReview key={`review:${goal}`} goal={goal} owner={activity.owner_id} project={activity.project_id} csrf={csrfFor('build')} deny={denyFor('build')}/>}
      {goal && <BuildEvidence key={`evidence:${goal}`} goal={goal} owner={activity.owner_id} project={activity.project_id} deny={denied}/>}
    </>}
    <footer>{phoneMode?'Private read-only status. Work runs on the workstation. Background views are cleared and rechecked on return. No background push or remote approvals.':<>Local desktop only. {owner?'Each session scope is paired and expires on its own; the CLI bearer token never enters this page. Final merge uses the existing separate owner CLI.':buildRunMode?'Exact PUBLIC plans can be staged, accepted and explicitly run once. Final merge uses the existing separate owner CLI. Phone access and full R3 acceptance remain unfinished.':askMode?'Offline Ask is available here. Delegate, Build intake and phone access remain separate R3 work.':researchMode?'PUBLIC questions can be staged here. Delegate execution, Build intake and phone access remain separate R3 work.':planAcceptanceMode?'Plans can be staged, reviewed and explicitly accepted here. Worker execution, final merge and phone access remain separate workflows.':buildIntakeMode?'PUBLIC plans can be staged here. Plan acceptance, execution, effect dispatch and phone access remain separate workflows.':reviewMode?'Consent records do not execute a merge. Job intake, effect dispatch and phone access remain separate R3 work.':'Job submission, approvals, evidence content and phone access remain separate unfinished R3 work.'}</>}</footer>
  </main>;
}
class Boundary extends Component<{children: ReactNode},{failed:boolean}> {
  state = {failed:false};
  static getDerivedStateFromError() {return {failed:true};}
  render() {return this.state.failed ? <main><h1>View unconfirmed</h1><p>Reload and pair again. Inspect canonical state before retrying any action.</p></main> : this.props.children;}
}
createRoot(document.getElementById('root')!).render(<Boundary><Dashboard/></Boundary>);
