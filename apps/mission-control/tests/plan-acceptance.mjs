import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {chromium,expect} from '@playwright/test';
const f=JSON.parse(readFileSync(process.env.PANESTRIA_BROWSER_FIXTURE,'utf8'));
const browser=await chromium.launch({headless:true});
try {
  const page=await browser.newPage();let accepts=0;page.on('request',r=>{if(r.method()==='POST' && new URL(r.url()).pathname.endsWith('/accept'))accepts++;});
  await page.goto(f.origin);await page.getByLabel('One-use pairing code from your terminal').fill(f.code);await page.getByRole('button',{name:'Pair',exact:true}).click();
  const view=page.getByRole('region',{name:'Build plan intake'});await view.getByLabel('PUBLIC plan bundle JSON',{exact:true}).fill(JSON.stringify(f.bundle));
  await view.getByRole('checkbox').check();await view.getByRole('button',{name:'Stage PUBLIC plan',exact:true}).click();
  await expect(view.getByTestId('build-intake-plan-state')).toHaveText('PROPOSED');
  await expect(view.getByRole('button',{name:'Accept exact plan',exact:true})).toBeDisabled();
  const retained=JSON.parse(await view.getByTestId('build-intake-retained').textContent());assert.deepEqual(retained.plan.proposal,f.bundle.proposal);
  await view.getByLabel('I reviewed the exact retained contract, checks, paths, DAG, inventory, budgets, digest and expiry.',{exact:false}).check();
  await view.getByRole('button',{name:'Accept exact plan',exact:true}).focus();await page.keyboard.press('Enter');
  await expect(view.getByTestId('build-intake-notice')).toContainText('UNCONFIRMED acceptance');await expect(view.getByRole('button',{name:'Accept exact plan',exact:true})).toHaveCount(0);assert.equal(accepts,1);
  await view.getByRole('button',{name:'Inspect staged plan',exact:true}).click();await expect(view.getByTestId('build-intake-plan-state')).toHaveText('ACCEPTED');await expect(view.getByTestId('build-intake-goal-state')).toHaveText('CREATED');assert.equal(accepts,1);
  await page.screenshot({path:process.env.PANESTRIA_BROWSER_SCREENSHOT,fullPage:true});
  await page.reload();await view.getByLabel('Recover staged plan by plan ID').fill(f.bundle.proposal.plan_id);await view.getByRole('button',{name:'Inspect staged plan',exact:true}).click();await expect(view.getByTestId('build-intake-plan-state')).toHaveText('ACCEPTED');assert.equal(accepts,1);
}finally{await browser.close();}
