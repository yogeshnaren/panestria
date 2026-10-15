'use strict';
let csrf = null, state = null, busy = false, refreshFailed = false;
const el = id => document.getElementById(id);
const message = text => { el('message').textContent = text; };
async function api(path, body) {
  const headers = {};
  if (body !== undefined) { headers['content-type'] = 'application/json'; headers['x-panestria-csrf'] = csrf || ''; }
  const result = await fetch(path, {method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', headers, body: body === undefined ? undefined : JSON.stringify(body)});
  const value = await result.json();
  if (!result.ok) throw Error(value.code || `Request failed (${result.status})`);
  return value;
}
function render(s) {
  state = s;
  el('ready').textContent = s.ready ? 'Qualified' : 'Pending';
  el('route').textContent = s.provider;
  el('reason').textContent = `${s.reason}${s.qualification ? ` · ${s.qualification.status}: ${s.qualification.reason}` : ''}`;
  el('policy').textContent = s.policy ? JSON.stringify({sha256: s.policy_sha256, certificate_sha256: s.certificate_sha256, policy: s.policy}, null, 2) : 'Qualification is required before a cloud task policy can be enabled.';
  el('intent').textContent = s.task;
  el('source').textContent = s.base_source;
  const goal = s.goal;
  const terminal = goal && ['COMPLETED', 'FAILED', 'CANCELLED', 'REJECTED'].includes(goal.status);
  el('start').disabled = busy || !s.ready || Boolean(goal && !terminal) || Boolean(goal && goal.status === 'COMPLETED');
  el('cancel').disabled = busy || !goal || terminal;
  el('status').textContent = goal ? `${goal.state} / ${goal.status}` : 'No run yet';
  el('goal-id').textContent = goal ? `Goal ${goal.id}` : '';
  el('interrupted').textContent = goal && ['VERIFYING', 'RECONCILING'].includes(goal.state) && !s.approval ? 'A recorded merge may need reconciliation. Do not start another worker; use the reconcile command in the instructions.' : '';
  el('events').replaceChildren(...(s.events || []).map(event => { const li = document.createElement('li'); li.textContent = `${event.seq} · ${event.kind}${event.payload.reason ? ` · ${event.payload.reason}` : ''}`; return li; }));
  el('diff').textContent = s.diff || 'Awaiting a generated and verified candidate.';
  el('candidate').textContent = s.evidence ? `Base ${s.evidence.base_commit} → candidate ${s.evidence.candidate_commit}` : '';
  el('checks').replaceChildren(...(s.evidence ? s.evidence.checks.map(check => { const p = document.createElement('p'); p.textContent = `${check.check_key}: ${check.verdict} (${check.reason})`; return p; }) : [document.createTextNode('No reports yet.')]));
  el('approval-section').hidden = !s.approval;
  el('preview').textContent = s.approval ? JSON.stringify({effect_digest: s.approval.effect_digest, ...s.approval.preview}, null, 2) : '';
  el('approve').disabled = el('deny').disabled = busy;
}
async function refresh() {
  if (!csrf || busy) return;
  try {
    render(await api('/v1/demo'));
    if (refreshFailed) { message('Connection restored.'); refreshFailed = false; }
  } catch (error) { refreshFailed = true; message(error.message); }
}
async function act(fn) {
  if (busy) return;
  busy = true; if (state) render(state);
  try { await fn(); message('Action recorded.'); } catch (error) { message(error.message); }
  finally { busy = false; await refresh(); }
}
el('pair-form').addEventListener('submit', async event => {
  event.preventDefault();
  try {
    const value = await api('/v1/session/pair', {code: el('code').value.toUpperCase()});
    csrf = value.csrf_token; el('code').value = ''; el('pair').hidden = true; el('review').hidden = false;
    message('Review session connected.'); await refresh();
  } catch (error) { message(error.message); }
});
el('start').addEventListener('click', () => act(async () => {
  const body = {goal_id: crypto.randomUUID(), certificate_sha256: state.certificate_sha256, policy_sha256: state.policy_sha256};
  await api('/v1/demo/start', body);
}));
el('cancel').addEventListener('click', () => act(() => api('/v1/demo/cancel', {goal_id: state.goal.id, expected_version: state.goal.version})));
for (const [id, decision] of [['approve', 'approve'], ['deny', 'deny']]) {
  el(id).addEventListener('click', () => act(() => api('/v1/demo/decision', {goal_id: state.goal.id, approval_id: state.approval.id, effect_digest: state.approval.effect_digest, expected_version: state.approval.version, decision, idempotency_key: crypto.randomUUID()})));
}
setInterval(refresh, 3000);
