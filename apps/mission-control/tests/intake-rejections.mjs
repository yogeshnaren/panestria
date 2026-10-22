import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {chromium,expect} from '@playwright/test';
const f=JSON.parse(readFileSync(process.env.PANESTRIA_BROWSER_FIXTURE,'utf8'));
const browser=await chromium.launch({headless:true});
try{
  const page=await browser.newPage();let posts=0;page.on('request',r=>{if(r.method()==='POST' && new URL(r.url()).pathname==='/v1/mission/build/plans')posts++;});
  await page.goto(f.origin);await page.getByLabel('One-use pairing code from your terminal').fill(f.code);await page.getByRole('button',{name:'Pair',exact:true}).click();
  const view=page.getByRole('region',{name:'Build plan intake'}),bad=structuredClone(f.bundle);bad.proposal.inventory_sha256='ff'.repeat(32);
  await view.getByLabel('PUBLIC plan bundle JSON',{exact:true}).fill(JSON.stringify(bad));await view.getByRole('checkbox').check();await view.getByRole('button',{name:'Stage PUBLIC plan',exact:true}).click();
  await expect(view.getByTestId('build-intake-notice')).toContainText('REJECTED BEFORE COMMIT');await expect(view.getByLabel('PUBLIC plan bundle JSON',{exact:true})).toBeEnabled();await expect(view.getByRole('checkbox')).not.toBeChecked();assert.equal(posts,1);
  await expect(view.getByTestId('build-intake-plan')).toHaveText(f.bundle.proposal.plan_id);
  await view.getByLabel('PUBLIC plan bundle JSON',{exact:true}).fill(JSON.stringify(f.bundle));await view.getByRole('checkbox').check();await view.getByRole('button',{name:'Stage PUBLIC plan',exact:true}).click();
  await expect(view.getByTestId('build-intake-plan-state')).toHaveText('PROPOSED');await expect(view.getByTestId('build-intake-plan')).toHaveText(f.bundle.proposal.plan_id);assert.equal(posts,2);
  await page.screenshot({path:process.env.PANESTRIA_BROWSER_SCREENSHOT,fullPage:true});
}finally{await browser.close();}
