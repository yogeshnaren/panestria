import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {chromium,expect} from '@playwright/test';
const f=JSON.parse(readFileSync(process.env.PANESTRIA_BROWSER_FIXTURE,'utf8'));
const browser=await chromium.launch({headless:true});
try {
  const page=await browser.newPage();let posts=0;page.on('request',r=>{if(r.method()==='POST' && new URL(r.url()).pathname==='/v1/mission/build/plans')posts++;});
  await page.goto(f.origin);await page.getByLabel('One-use pairing code from your terminal').fill(f.code);await page.getByRole('button',{name:'Pair',exact:true}).click();
  const view=page.getByRole('region',{name:'Build plan intake'});await expect(view).toBeVisible();
  await view.getByLabel('Load PUBLIC plan bundle file',{exact:true}).setInputFiles({name:'public-bundle.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(f.first,null,2))});
  await expect(view.getByRole('button',{name:'Stage PUBLIC plan',exact:true})).toBeDisabled();
  await view.getByRole('checkbox').check();await view.getByRole('button',{name:'Stage PUBLIC plan',exact:true}).click();
  await expect(view.getByTestId('build-intake-plan-state')).toHaveText('PROPOSED');await expect(view.getByTestId('build-intake-goal-state')).toHaveText('CREATED');
  await view.getByText('Exact retained contract, proposal, inventory and validation',{exact:true}).click();await expect(view.getByTestId('build-intake-retained')).toContainText(f.first.proposal.contract_sha256);
  assert.deepEqual(JSON.parse(await view.getByTestId('build-intake-retained').textContent()).plan.proposal,f.first.proposal);
  await expect(view.locator('script,img')).toHaveCount(0);assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
  await page.screenshot({path:process.env.PANESTRIA_BROWSER_SCREENSHOT,fullPage:true});
  await view.getByRole('button',{name:'New PUBLIC plan',exact:true}).click();await view.getByLabel('PUBLIC plan bundle JSON',{exact:true}).fill(JSON.stringify(f.second));
  await view.getByRole('checkbox').check();await view.getByRole('button',{name:'Stage PUBLIC plan',exact:true}).click();
  await expect(view.getByTestId('build-intake-notice')).toContainText('UNCONFIRMED');await expect(view.getByRole('button',{name:'Stage PUBLIC plan',exact:true})).toBeDisabled();
  await view.getByRole('button',{name:'Inspect staged plan',exact:true}).click();await expect(view.getByTestId('build-intake-plan-state')).toHaveText('PROPOSED');assert.equal(posts,2);
  await page.reload();await expect(view.getByLabel('PUBLIC plan bundle JSON',{exact:true})).toHaveValue('');
  await view.getByLabel('Recover staged plan by plan ID').fill(f.first.proposal.plan_id);await view.getByRole('button',{name:'Inspect staged plan',exact:true}).click();
  await expect(view.getByTestId('build-intake-plan-state')).toHaveText('PROPOSED');await expect(view.getByTestId('build-intake-plan')).toHaveText(f.first.proposal.plan_id);assert.equal(posts,2);
} finally {await browser.close();}
