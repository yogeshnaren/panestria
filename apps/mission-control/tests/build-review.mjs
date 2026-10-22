import {chromium,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {createInterface} from 'node:readline';
import assert from 'node:assert/strict';
const f=JSON.parse(readFileSync(process.env.PANESTRIA_BROWSER_FIXTURE,'utf8'));
const lines=createInterface({input:process.stdin})[Symbol.asyncIterator]();
const browser=await chromium.launch({headless:true});
try {
 const context=await browser.newContext();const page=await context.newPage();const errors=[], networkFailures=[];
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
 // Focus while online. A mouse click waits for layout stability and may wait
 // forever for controls that a concurrent offline read correctly removes.
 await approve.focus();await context.setOffline(true);await page.keyboard.press('Enter');
 // Either the decision transport fails or the concurrent protected read fences
 // the form before submission. Both must hide content, grant no consent and
 // recover the canonical PENDING request; neither is an optimistic decision.
 await expect(section).toContainText('UNCONFIRMED');
 await expect(section.getByLabel('Protected diff')).toHaveCount(0);
 assert(networkFailures.some(path=>path.endsWith('/build-review') || path.endsWith('/build-review/decision')));
 await context.setOffline(false);
 const reopen=section.getByRole('button',{name:'Review exact merge request',exact:true});
 if(await reopen.isVisible()) await reopen.click();
 else await section.getByRole('button',{name:'Refresh exact review',exact:true}).click();
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
