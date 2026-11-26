// The owner app (`panestria serve`) on physical loopback HTTP and PostgreSQL, with
// production assets. Only the model, hardware and Build run service are Python
// fixtures. Each pairing code comes from `panestria pair-code`, as in the terminal.
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import assert from 'node:assert/strict';
import {chromium, expect} from '@playwright/test';
const f = JSON.parse(readFileSync(process.env.PANESTRIA_BROWSER_FIXTURE,'utf8'));
const name = {activity:'Activity', ask:'Ask', build:'Build'};
function code(scope) {
  const issued = JSON.parse(execFileSync(f.python,['-m','panestria.cli.main','pair-code','--config',f.config,'--scope',scope],
    {encoding:'utf8',timeout:15000}));
  assert.equal(issued.scope,scope);
  return issued.code;
}
const hours = iso => (Date.parse(iso)-Date.now())/3600000;
const browser = await chromium.launch({headless:true});
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  const csrf = {};
  page.on('request',request => {
    if (request.method()==='POST') (csrf[new URL(request.url()).pathname] ??= []).push(request.headers()['x-panestria-csrf'] ?? null);
  });
  // Requests and responses in arrival order, so a check can follow the activity
  // read that the page issues after an action's response (not an earlier poll).
  const events = [];
  page.on('request',request => events.push({type:'request', path:new URL(request.url()).pathname, request}));
  page.on('response',response => events.push({type:'response', path:new URL(response.url()).pathname, request:response.request()}));
  async function readAfter(action, path) {
    const mark = events.length;
    await action();
    let read;
    await expect.poll(() => {
      const tail = events.slice(mark), at = tail.findIndex(e => e.type==='response' && e.path===path);
      read = at < 0 ? undefined : tail.slice(at+1).find(e => e.type==='request' && e.path==='/v1/activity');
      return Boolean(read);
    }).toBe(true);
    return String((await read.request.response()).status());
  }
  const row = scope => page.getByRole('region',{name:`${name[scope]} session`,exact:true});
  const state = scope => row(scope).getByTestId(`session-${scope}`);
  const notice = scope => row(scope).getByTestId(`session-${scope}-notice`);
  const sessions = {};
  async function pair(scope, value) {
    const reply = page.waitForResponse(r => new URL(r.url()).pathname===`/v1/session/${scope}/pair`);
    await row(scope).getByRole('textbox').fill(value);
    await row(scope).getByRole('button',{name:`Pair ${name[scope]}`,exact:true}).click();
    const response = await reply;
    if (response.ok()) (sessions[scope] ??= []).push(await response.json());
    return response;
  }
  const activity = page.getByRole('region',{name:'Project activity'});
  const ask = page.getByRole('region',{name:'Offline Ask'});
  const intake = page.getByRole('region',{name:'Build plan intake'});
  async function inspectPlan() {
    await intake.getByLabel('Recover staged plan by plan ID').fill(f.plan);
    await intake.getByRole('button',{name:'Inspect staged plan',exact:true}).click();
  }

  await page.goto(f.origin);
  if (f.mismatch) {
    // The page leaves out a scope the server mounts: the authenticated
    // capabilities disagree with the page, so nothing is shown.
    await expect(page.getByText(/^PANESTRIA · OWNER · ASK/)).toBeVisible();
    await expect(row(f.mismatch)).toHaveCount(0);
    assert.ok((await pair('ask',code('ask'))).ok());
    await expect(page.getByText('This page and the server disagree on session scopes. Nothing new is shown; reload the page.',{exact:true})).toBeVisible();
    await expect(activity).toHaveCount(0);
    await expect(ask).toHaveCount(0);
    console.log(JSON.stringify({mismatch:f.mismatch}));
    await browser.close();
    process.exit(0);
  }
  await expect(page.getByText('PANESTRIA · OWNER · ASK AND BUILD',{exact:true})).toBeVisible();
  for (const scope of ['activity','ask','build']) await expect(state(scope)).toHaveText('Not paired in this tab.');
  await expect(activity).toHaveCount(0);

  // An Ask session reaches Ask and activity, and lasts a working day.
  assert.ok((await pair('ask',code('ask'))).ok());
  await expect(state('ask')).toContainText('Paired in this tab until');
  const askHours = hours(sessions.ask[0].expires_at);
  assert.ok(askHours > 7.9 && askHours <= 8, String(askHours));
  await expect(activity).toBeVisible();
  await ask.getByLabel('Question',{exact:true}).fill('Say READY');
  await ask.getByRole('button',{name:'Ask offline',exact:true}).click();
  await expect(ask.getByTestId('ask-state')).toHaveText('COMPLETED');
  await expect(ask.getByTestId('ask-answer')).toHaveText('READY');
  const asked = await ask.getByTestId('ask-id').textContent();

  // A Build route refuses the Ask session. Only Build is marked unpaired; Ask stays.
  await inspectPlan();
  await expect(notice('build')).toHaveText(/^Build session required\./);
  await expect(state('ask')).toContainText('Paired in this tab until');
  await expect(ask.getByTestId('ask-answer')).toHaveText('READY');

  // A Build code from the CLI pairs Build for one hour. (The five pairings in this
  // journey are the whole per-minute pairing budget, shared by every scope.)
  assert.ok((await pair('build',code('build'))).ok());
  await expect(state('build')).toContainText('Paired in this tab until');
  const buildHours = hours(sessions.build[0].expires_at);
  assert.ok(buildHours > 0.95 && buildHours <= 1, String(buildHours));
  await inspectPlan();
  await expect(intake.getByTestId('build-intake-notice')).toHaveText('Plan unavailable or unconfirmed in this project. No action was sent.');
  await expect(notice('build')).toHaveText('Build paired in this tab.');
  // With Ask and Build both paired, Ask still sends Ask's own CSRF token.
  await ask.getByRole('button',{name:'New question',exact:true}).click();
  await ask.getByLabel('Question',{exact:true}).fill('Say READY again');
  await ask.getByRole('button',{name:'Ask offline',exact:true}).click();
  await expect(ask.getByTestId('ask-state')).toHaveText('COMPLETED');
  await page.screenshot({path:process.env.PANESTRIA_BROWSER_SCREENSHOT,fullPage:true});

  // Logging out of Build ends Build only, with Build's own CSRF token.
  assert.equal(await readAfter(()=>row('build').getByRole('button',{name:'Log out of Build',exact:true}).click(),'/v1/session/build/logout'),'200');
  await expect(notice('build')).toHaveText('Build session revoked.');
  await expect(state('build')).toHaveText('Not paired in this tab.');
  await expect(state('ask')).toContainText('Paired in this tab until');
  const [askToken, askAgain] = csrf['/v1/ask'], [buildToken] = csrf['/v1/session/build/logout'];
  assert.ok(askToken && buildToken && askToken!==buildToken && askAgain===askToken);
  await inspectPlan();
  await expect(notice('build')).toHaveText(/^Build session required\./);
  await expect(state('ask')).toContainText('Paired in this tab until');

  // The browser drops the Build cookie when its hour is up. The next Build read
  // is refused: this tab's Build session ends there, and Ask still reads activity.
  assert.ok((await pair('build',code('build'))).ok());
  await context.clearCookies({name:/^panestria_owner_build_/});
  assert.equal(await readAfter(inspectPlan,`/v1/mission/build/plans/${f.plan}`),'200');
  await expect(notice('build')).toHaveText(/^Build session required\./);
  await expect(state('build')).toHaveText('Not paired in this tab.');
  await expect(state('ask')).toContainText('Paired in this tab until');

  // CSRF tokens are memory-only: after a reload nothing is paired in this tab,
  // while the surviving Ask cookie still reads activity and Ask receipts.
  await page.reload();
  for (const scope of ['activity','ask','build']) await expect(state(scope)).toHaveText('Not paired in this tab.');
  await expect(activity).toBeVisible();
  await expect(ask).toContainText('Pair again to submit or cancel.');
  await ask.getByLabel('Recover receipt by request ID').fill(asked);
  await ask.getByRole('button',{name:'Inspect receipt',exact:true}).click();
  await expect(ask.getByTestId('ask-state')).toHaveText('COMPLETED');
  await expect(page.getByRole('button',{name:/^Log out/})).toHaveCount(0);

  // An activity session logs out alone; the Ask cookie still reads activity.
  assert.ok((await pair('activity',code('activity'))).ok());
  assert.equal(await readAfter(()=>row('activity').getByRole('button',{name:'Log out of Activity',exact:true}).click(),'/v1/session/activity/logout'),'200');
  await expect(notice('activity')).toHaveText('Activity session revoked.');
  await expect(activity).toBeVisible();

  // With the last session logged out, the dashboard shows nothing until paired again.
  assert.ok((await pair('ask',code('ask'))).ok());
  assert.equal(await readAfter(()=>row('ask').getByRole('button',{name:'Log out of Ask',exact:true}).click(),'/v1/session/ask/logout'),'401');
  await expect(activity).toHaveCount(0);
  await expect(ask).toHaveCount(0);
  await expect(page.getByText('Project unconfirmed. Pair or retry when the server is available.',{exact:true})).toBeVisible();
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
  console.log(JSON.stringify({asked, sessions:Object.fromEntries(Object.entries(sessions).map(([k,v])=>[k,v.map(s=>s.session_id)]))}));
  await context.close();
} finally {await browser.close();}
