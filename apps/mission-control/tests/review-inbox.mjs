import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {chromium,expect} from '@playwright/test';
const f=JSON.parse(readFileSync(process.env.PANESTRIA_BROWSER_FIXTURE,'utf8'));
const browser=await chromium.launch({headless:true});
try{
  const context=await browser.newContext(),page=await context.newPage();let actions=0;
  page.on('request',r=>{if(r.method()==='POST' && new URL(r.url()).pathname.startsWith('/v1/mission/build/plans'))actions++;});
  await page.goto(f.origin);await page.getByLabel('One-use pairing code from your terminal').fill(f.code);await page.getByRole('button',{name:'Pair',exact:true}).click();
  const inbox=page.getByRole('region',{name:'Pending review inbox'}),view=page.getByRole('region',{name:'Build plan intake'});
  await expect(inbox.locator('[data-review-id]')).toHaveCount(3);await expect(inbox).not.toContainText('PRIVATE_PREVIEW');assert.equal(actions,0);
  const row=inbox.locator(`[data-review-id="${f.plan}"]`);await row.getByRole('button',{name:'Select plan for inspection',exact:true}).click();
  await expect(view.getByLabel('Recover staged plan by plan ID')).toHaveValue(f.plan);assert.equal(actions,0);
  await view.getByRole('button',{name:'Inspect staged plan',exact:true}).click();await expect(view.getByTestId('build-intake-plan-state')).toHaveText('PROPOSED');
  await view.getByLabel('I reviewed the exact retained contract, checks, paths, DAG, inventory, budgets, digest and expiry.',{exact:false}).check();await view.getByRole('button',{name:'Accept exact plan',exact:true}).click();await expect(view.getByTestId('build-intake-plan-state')).toHaveText('ACCEPTED');assert.equal(actions,1);
  await inbox.getByRole('button',{name:'First page / refresh reviews',exact:true}).click();await expect(row).toHaveCount(0);await expect(inbox.locator('[data-review-id]')).toHaveCount(2);
  await page.screenshot({path:process.env.PANESTRIA_BROWSER_SCREENSHOT,fullPage:true});
  await context.setOffline(true);await inbox.getByRole('button',{name:'First page / refresh reviews',exact:true}).click();await expect(inbox.getByTestId('inbox-notice')).toContainText('UNCONFIRMED');await expect(inbox.locator('[data-review-id]')).toHaveCount(0);
  await context.setOffline(false);await inbox.getByRole('button',{name:'First page / refresh reviews',exact:true}).click();await expect(inbox.locator('[data-review-id]')).toHaveCount(2);assert.equal(actions,1);
  await page.getByRole('button',{name:'Log out',exact:true}).click();await expect(inbox).toHaveCount(0);
}finally{await browser.close();}
