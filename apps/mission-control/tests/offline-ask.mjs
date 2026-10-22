// Production assets, physical loopback HTTP/Postgres. Only the model/process/
// hardware are Python fixtures. No route mocking, browser storage or provider fallback.
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {chromium, expect} from '@playwright/test';
const fixture = JSON.parse(readFileSync(process.env.PANESTRIA_BROWSER_FIXTURE,'utf8'));
const browser = await chromium.launch({headless:true});
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  const outcomes = {};
  await page.goto(fixture.origin);
  await page.getByLabel('One-use pairing code from your terminal').fill(fixture.code);
  await page.getByRole('button',{name:'Pair',exact:true}).click();
  const ask = page.getByRole('region',{name:'Offline Ask'});
  await expect(ask).toBeVisible();
  await ask.getByLabel('Question',{exact:true}).fill('é'.repeat(2100));
  await expect(ask.getByRole('button',{name:'Ask offline',exact:true})).toBeDisabled();
  async function submit(question) {
    await ask.getByLabel('Question',{exact:true}).fill(question);
    await ask.getByRole('button',{name:'Ask offline',exact:true}).click();
    await expect(ask.getByTestId('ask-id')).toHaveText(/[0-9a-f-]{36}/);
    return await ask.getByTestId('ask-id').textContent();
  }
  async function state(id, value) {
    await expect.poll(async()=>{
      const response = await context.request.get(`${fixture.origin}/v1/ask/${id}`);
      return response.ok() ? (await response.json()).state : 'UNAVAILABLE_READ';
    },{timeout:10000}).toBe(value);
  }
  const completed = await submit('SYNTHETIC_MISSION_ASK: show literal markup.');
  await expect(ask.getByTestId('ask-state')).toHaveText('COMPLETED');
  await expect(ask.getByTestId('ask-answer')).toContainText('<img src=x');
  assert.equal(await page.evaluate(()=>window.askInjected),undefined);
  await expect(ask.locator('img,script')).toHaveCount(0);
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
  await page.screenshot({path:process.env.PANESTRIA_BROWSER_SCREENSHOT,fullPage:true});
  outcomes[completed]='COMPLETED';
  await ask.getByRole('button',{name:'New question',exact:true}).click();
  const cancelled = await submit('SYNTHETIC WAIT_FOR_CANCEL explicit');
  await state(cancelled,'RUNNING');
  await ask.getByRole('button',{name:'Cancel request',exact:true}).click();
  await expect(ask.getByTestId('ask-notice')).toContainText('Canonical request state: CANCELLED');
  await expect(ask.getByTestId('ask-answer')).toHaveCount(0);
  await state(cancelled,'CANCELLED');outcomes[cancelled]='CANCELLED';
  await ask.getByRole('button',{name:'New question',exact:true}).click();
  const disconnected = await submit('SYNTHETIC WAIT_FOR_CANCEL disconnect');
  await state(disconnected,'RUNNING');
  await context.setOffline(true);
  await expect(ask.getByTestId('ask-notice')).toContainText('UNCONFIRMED',{timeout:10000});
  await expect(ask.getByRole('button',{name:'Ask offline',exact:true})).toBeDisabled();
  await expect(ask.getByRole('button',{name:'New question',exact:true})).toHaveCount(0);
  await context.setOffline(false);
  await state(disconnected,'CANCELLED');
  await ask.getByRole('button',{name:'Inspect receipt',exact:true}).click();
  await expect(ask.getByTestId('ask-state')).toHaveText('CANCELLED');outcomes[disconnected]='CANCELLED';
  await ask.getByRole('button',{name:'New question',exact:true}).click();
  const unavailable = await submit('SYNTHETIC MODEL_UNAVAILABLE');
  await expect(ask.getByTestId('ask-state')).toHaveText('UNAVAILABLE');
  await expect(ask.getByTestId('ask-answer')).toHaveCount(0);outcomes[unavailable]='UNAVAILABLE';
  await page.reload();
  await ask.getByLabel('Recover receipt by request ID').fill(completed);
  await ask.getByRole('button',{name:'Inspect receipt',exact:true}).click();
  await expect(ask.getByTestId('ask-state')).toHaveText('COMPLETED');
  await expect(ask.getByTestId('ask-answer')).toHaveCount(0);
  await expect(ask.getByTestId('ask-notice')).toContainText('cannot recover answer text');
  await expect(page.getByRole('button',{name:'Log out',exact:true})).toHaveCount(0);
  console.log(JSON.stringify(outcomes));
  await context.close();
} finally {await browser.close();}
