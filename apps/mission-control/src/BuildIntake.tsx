import {useEffect,useRef,useState,type FormEvent} from 'react';
import {Denied,json} from './client';
import type {components,operations} from './schema';
type Receipt=components['schemas']['BuildPlanStagingView'];
type Submission=operations['stage_plan_v1_mission_build_plans_post']['requestBody']['content']['application/json'];
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const bytes=(value:string)=>new TextEncoder().encode(value).length;

export function BuildIntake({owner,project,csrf,deny}:{owner:string,project:string,csrf:string|null,deny:()=>void}) {
  const [raw,setRaw]=useState(''),[confirmed,setConfirmed]=useState(false),[lookup,setLookup]=useState('');
  const [plan,setPlan]=useState(''),[receipt,setReceipt]=useState<Receipt|null>(null),[pending,setPending]=useState(false),[uncertain,setUncertain]=useState(false);
  const [notice,setNotice]=useState('Load an existing PUBLIC contract, proposal and inventory bundle. Review it before staging.');
  const busy=useRef(false),controller=useRef(new AbortController()),denyRef=useRef(deny);denyRef.current=deny;
  useEffect(()=>{const current=controller.current;const clear=()=>{setRaw('');setReceipt(null);setConfirmed(false);};
    window.addEventListener('pagehide',clear);return()=>{current.abort();window.removeEventListener('pagehide',clear);};},[owner,project]);
  function parse():Submission {
    const value=JSON.parse(raw);
    if(!value || typeof value!=='object' || Object.keys(value).sort().join(',')!=='contract_document,inventory,proposal' ||
       !value.contract_document || !value.proposal || !value.inventory)throw new Error('Invalid bundle');
    for(const document of [value.contract_document,value.proposal,value.inventory])
      if(document.owner_id!==owner || document.project_id!==project)throw new Error('Wrong scope');
    if(value.contract_document.privacy_class!=='PUBLIC' || value.proposal.privacy_class!=='PUBLIC' ||
       value.contract_document.budget?.max_api_usd!=='0' || !uuid.test(value.proposal.plan_id) ||
       value.proposal.goal_id!==value.contract_document.goal_id)throw new Error('PUBLIC zero-cash plan required');
    const body:Submission={...value,public_plan:true};if(bytes(JSON.stringify(body))>65536)throw new Error('Bundle too large');return body;
  }
  let preview:Submission|null=null;try{preview=parse();}catch{/* Server remains the canonical validator. */}
  function validate(value:Receipt,id:string) {
    if(value.owner_id!==owner || value.project_id!==project || value.plan?.proposal.plan_id!==id ||
       value.plan.proposal.owner_id!==owner || value.plan.proposal.project_id!==project ||
       value.goal_id!==value.plan.proposal.goal_id || value.operation!=='STAGED_NO_EXECUTION' ||
       value.execution_authority!=='NONE' || value.plan.execution_authority!=='NONE' ||
       !['PROPOSED','ACCEPTED'].includes(value.plan.state))throw new Error('Unconfirmed plan');return value;
  }
  async function submit(event:FormEvent) {
    event.preventDefault();if(!csrf || busy.current || uncertain || receipt || !confirmed)return;
    let body:Submission;try{body=parse();}catch{setNotice('Invalid, oversized or differently scoped bundle. Nothing submitted.');return;}
    const id=body.proposal.plan_id as string;busy.current=true;setPending(true);setUncertain(true);setPlan(id);setLookup(id);setReceipt(null);
    setNotice('Staging the exact PUBLIC bundle locally. No acceptance or worker launch.');
    try {
      const value=validate(await json<Receipt>('/v1/mission/build/plans',controller.current.signal,body,csrf),id);
      if(controller.current.signal.aborted)return;setReceipt(value);setUncertain(false);setNotice('STAGED_NO_EXECUTION. Inspect the canonical contract, proposal, validation and consent below.');
    }catch(error){if(controller.current.signal.aborted)return;if(error instanceof Denied)denyRef.current();else setNotice('UNCONFIRMED. Inspect this plan ID before another submission. No automatic POST retry was sent.');}
    finally{busy.current=false;setPending(false);}
  }
  async function inspect(event:FormEvent) {
    event.preventDefault();if(busy.current)return;const id=(uncertain?plan:lookup).trim();if(!uuid.test(id)){setNotice('Enter a plan UUID.');return;}
    busy.current=true;setPending(true);setReceipt(null);
    try{const value=validate(await json<Receipt>(`/v1/mission/build/plans/${id}`,controller.current.signal),id);
      if(controller.current.signal.aborted)return;setReceipt(value);setPlan(id);setLookup(id);setRaw('');setConfirmed(false);setUncertain(false);setNotice('Canonical plan inspected. No resubmission, acceptance or execution.');
    }catch(error){if(controller.current.signal.aborted)return;if(error instanceof Denied)denyRef.current();else setNotice('Plan unavailable or unconfirmed in this project. No action was sent.');}
    finally{busy.current=false;setPending(false);}
  }
  return <section aria-label="Build plan intake"><h2>Build · stage a PUBLIC plan</h2>
    <p>Import an existing contract, plan proposal and project inventory from the owner CLI or local planner. Staging validates and retains the plan; it creates no task, attempt or worker. Inventory declarations are not runtime qualification.</p>
    <p role="status" data-testid="build-intake-notice">{notice}</p>
    <form onSubmit={submit}><label htmlFor="build-bundle-file">Load PUBLIC plan bundle file</label><input id="build-bundle-file" type="file" accept=".json,application/json" disabled={pending || uncertain || !!receipt}
      onChange={async e=>{const input=e.currentTarget,file=input.files?.[0];input.value='';if(!file)return;
        if(file.size>65536){setNotice('File exceeds 65536 bytes. Nothing loaded.');return;}
        try{const text=await file.text();if(!controller.current.signal.aborted){setRaw(text);setConfirmed(false);setNotice('File loaded in memory. Review the complete PUBLIC bundle.');}}
        catch{setNotice('File unavailable. Nothing submitted.');}}}/>
      <label htmlFor="build-bundle">PUBLIC plan bundle JSON</label><textarea id="build-bundle" rows={12} value={raw} maxLength={65536} spellCheck={false} autoComplete="off"
        onChange={e=>{setRaw(e.target.value);setConfirmed(false);}} disabled={pending || uncertain || !!receipt}/>
      <p className="muted">{bytes(raw)} bytes. Maximum complete request: 65536 UTF-8 bytes. Keys: contract_document, proposal, inventory. Existing IDs, hashes, budgets, checks and paths are preserved.</p>
      {preview && <p>Selected plan <code>{String(preview.proposal.plan_id)}</code> · goal <code>{String(preview.proposal.goal_id)}</code>. The server validates the full DAG, scope and current policy.</p>}
      <label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)} disabled={pending || uncertain || !!receipt}/>I reviewed this entire bundle and confirm all its content is PUBLIC. Stage only; do not accept or execute it.</label>
      <div className="actions"><button disabled={!preview || !csrf || !confirmed || pending || uncertain || !!receipt}>Stage PUBLIC plan</button>
        {receipt && <button type="button" disabled={pending} onClick={()=>{setReceipt(null);setRaw('');setPlan('');setLookup('');setConfirmed(false);setNotice('Ready to review another PUBLIC plan bundle.');}}>New PUBLIC plan</button>}</div>
    </form>
    {plan && <p>Plan ID <code data-testid="build-intake-plan">{plan}</code></p>}
    <form onSubmit={inspect}><label htmlFor="build-plan-lookup">Recover staged plan by plan ID</label><div className="actions">
      <input id="build-plan-lookup" className="receipt-id" value={lookup} onChange={e=>setLookup(e.target.value)} disabled={pending || uncertain} autoComplete="off" spellCheck={false}/>
      <button disabled={pending || !(uncertain?plan:lookup).trim()}>Inspect staged plan</button></div></form>
    {receipt && <div aria-label="Canonical staged plan"><p>Operation <strong>STAGED_NO_EXECUTION</strong> · execution authority NONE · runtime qualification NOT_ASSESSED</p>
      <p>Goal <strong data-testid="build-intake-goal-state">{receipt.goal_status}</strong> · plan <strong data-testid="build-intake-plan-state">{receipt.plan.state}</strong></p>
      <p>Consent digest <code>{receipt.plan.effect_digest}</code> · expires <code>{receipt.plan.consent.expires_at}</code>.</p>
      <p>Plan acceptance, scheduling, worker execution and final merge require separate existing owner workflows. An expired pending consent cannot be accepted.</p>
      <details><summary>Exact retained contract, proposal, inventory and validation</summary><pre data-testid="build-intake-retained">{JSON.stringify(receipt,null,2)}</pre></details>
    </div>}
  </section>;
}
