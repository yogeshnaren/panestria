import {chromium,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {createInterface} from 'node:readline';
import assert from 'node:assert/strict';
const f=JSON.parse(readFileSync(process.env.PANESTRIA_BROWSER_FIXTURE,'utf8'));
const lines=createInterface({input:process.stdin})[Symbol.asyncIterator]();
const browser=await chromium.launch({headless:true});
try {
 const context=await browser.newContext();const page=await context.newPage();const errors=[], networkFailures=[];
 // Actual offline fetch still fails. Delay only delivery of that failure to
 // React, so recovery cannot race an in-flight consent request as it did in CI.
 await page.addInitScript(()=>{
   let release;const reported=new Promise(resolve=>{release=resolve;});
   const fault={enabled:false,decisionFailed:false,release:()=>{fault.enabled=false;release();}};
   window.__reviewFailureFault=fault;
   const original=window.fetch.bind(window);
   window.fetch=async (...args)=>{
     try{return await original(...args);}
     catch(error){
       const input=args[0];const path=new URL(input instanceof Request?input.url:String(input),location.href).pathname;
       if(fault.enabled && (path.endsWith('/build-review') || path.endsWith('/build-review/decision'))){
         if(path.endsWith('/decision'))fault.decisionFailed=true;
         await reported;
       }
       throw error;
     }
   };
 });
 page.on('pageerror',e=>errors.push(e.message));
 page.on('requestfailed',r=>networkFailures.push(new URL(r.url()).pathname));
 await page.goto(f.origin);
 await page.getByLabel('One-use pairing code from your terminal').fill(f.code);
 await page.getByRole('button',{name:'Pair',exact:true}).click();
 await page.getByRole('button',{name:`Open goal ${f.goal.slice(0,8)}`,exact:true}).click();
 const section=page.getByRole('region',{name:'Exact Build review'});
 await section.getByRole('button',{name:'Review exact merge request',exact:true}).click();
 await expect(section.getByLabel('Protected diff')).toContainText('+value = 43');
 // Parent reconciliation must preserve the one open review and its evidence
 // sibling across a canonical activity refresh (previously their keys collided).
 const observed=await page.getByRole('region',{name:'Project activity'}).getByText(/^Observed /).textContent();
 await expect.poll(()=>page.getByRole('region',{name:'Project activity'}).getByText(/^Observed /).textContent(),{timeout:15000}).not.toBe(observed);
 await expect(section).toHaveCount(1);
 await expect(page.getByRole('region',{name:'Verified Build progress'})).toHaveCount(1);
 await expect(section.getByLabel('Protected diff')).toContainText('+value = 43');
 await expect(section.getByLabel('Protected diff')).toContainText('<img src=x onerror=');
 assert.equal(await page.title(),'Panestria Mission Control');
 await expect(section).toContainText('approval PENDING');
 await expect(section.getByLabel('Canonical merge preview')).toContainText('refs/heads/main@');
 const input=section.getByLabel('Type the exact effect digest to confirm this preview');
 await input.fill('0'.repeat(64));
 await section.getByRole('checkbox').check();
 const approve=section.getByRole('button',{name:'Record approval',exact:true});
 await expect(approve).toBeDisabled();
 const digest=await section.getByTestId('review-effect-digest').textContent();
 await input.fill(digest);await expect(approve).toBeEnabled();
 // Hold failed read notifications until after this actual keyboard submission;
 // then hold the failed decision's notification while inspecting the pending UI.
 await approve.focus();await page.evaluate(()=>{window.__reviewFailureFault.enabled=true;});
 await context.setOffline(true);await page.keyboard.press('Enter');
 await expect.poll(()=>page.evaluate(()=>window.__reviewFailureFault.decisionFailed)).toBe(true);
 await expect(section).toHaveAttribute('aria-busy','true');
 await expect(section).toContainText('UNCONFIRMED');
 await expect(section.getByLabel('Protected diff')).toHaveCount(0);
 await expect(section.getByRole('button',{name:'Refresh exact review',exact:true})).toBeDisabled();
 assert(networkFailures.some(path=>path.endsWith('/build-review/decision')));
 if(process.env.PANESTRIA_BROWSER_PENDING_SCREENSHOT)
   await page.screenshot({path:process.env.PANESTRIA_BROWSER_PENDING_SCREENSHOT,fullPage:true});
 await page.evaluate(()=>window.__reviewFailureFault.release());
 // A read error or stale label is not proof that the consent attempt finished.
 // Settle it while still offline before choosing the canonical recovery action.
 await expect(section).toHaveAttribute('aria-busy','false');
 await context.setOffline(false);
 const reopen=section.getByRole('button',{name:'Review exact merge request',exact:true});
 await expect(reopen).toBeEnabled();await reopen.click();
 await expect(section).toContainText('approval PENDING');
 await input.fill(await section.getByTestId('review-effect-digest').textContent());
 await section.getByRole('checkbox').check();
 await approve.focus();await page.keyboard.press('Enter');
 await expect(section).toContainText('Consent APPROVED. No merge dispatched.');
 assert.equal(await page.locator('img,script[src^="https:"],iframe').count(),0);
 assert.equal(await page.evaluate(()=>localStorage.length),0);
 await page.screenshot({path:process.env.PANESTRIA_BROWSER_SCREENSHOT,fullPage:true});
 console.log('APPROVED');assert(!(await lines.next()).done);
 await expect(page.getByTestId('goal-state')).toHaveText('COMPLETED',{timeout:25000});
 await page.getByRole('button',{name:'Inspect Build evidence',exact:true}).click();
 await expect(page.getByRole('region',{name:'Verified Build progress'})).toContainText('owner merge CONFIRMED');
 assert.deepEqual(errors,[]);console.log('PASS');
} finally {await browser.close();}
