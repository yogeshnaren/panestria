import {chromium,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {createInterface} from 'node:readline';
import assert from 'node:assert/strict';
const f=JSON.parse(readFileSync(process.env.PANESTRIA_BROWSER_FIXTURE,'utf8'));
const lines=createInterface({input:process.stdin})[Symbol.asyncIterator]();
async function step(name){console.log(name);assert(!(await lines.next()).done);}
const browser=await chromium.launch({headless:true});
try{
 // UX-only mobile emulation, not a real phone/certificate qualification.
 const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,ignoreHTTPSErrors:true});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 // Observe the real browser fetch body inside its renderer. Chromium can discard
 // the no-store body before CDP's Network.getResponseBody, even on response events.
 // Clone only this response; preserve the actual request, cookie, headers and body.
 await page.addInitScript(()=>{
  const fetch=window.fetch.bind(window);
  window.__panestriaPairResponse=new Promise((resolve,reject)=>{
   window.fetch=async(...args)=>{
    const response=await fetch(...args);
    if(new URL(response.url).pathname==='/v1/session/pair'){
     try{resolve({status:response.status,body:await response.clone().json()});}
     catch(error){reject(error);throw error;}
    }
    return response;
   };
  });
 });
 await page.goto(f.origin);
 await expect(page.locator('header')).toContainText('PRIVATE PHONE OBSERVER');
 await expect(page.locator('footer')).toContainText('No background push or remote approvals');
 await page.getByLabel('One-use pairing code from your terminal').fill(f.code);
 await page.getByRole('button',{name:'Pair',exact:true}).click();
 const paired=await page.evaluate(()=>window.__panestriaPairResponse);
 await page.evaluate(()=>{delete window.__panestriaPairResponse;});
 assert.equal(paired.status,200);const csrf=paired.body.csrf_token;
 assert.equal(typeof csrf,'string');assert(csrf.length>0);
 const project=page.getByRole('region',{name:'Project activity'});
 const inbox=page.getByRole('region',{name:'Pending review inbox'});
 await expect(project).toBeVisible();await expect(page.getByTestId('project-freshness')).toContainText('Confirmed');
 await page.getByRole('button',{name:`Open goal ${f.goal.slice(0,8)}`,exact:true}).click();
 await page.getByRole('button',{name:'Inspect Build evidence',exact:true}).click();
 const evidence=page.getByRole('region',{name:'Verified Build progress'});
 await expect(evidence.getByRole('progressbar')).toHaveAttribute('value','0');
 await step('RUN');
 await expect(evidence).toContainText('owner merge PENDING',{timeout:25000});
 await expect(evidence).toContainText('Goal ACTIVE');await expect(evidence).toContainText('release acceptance NOT_ASSESSED');
 await expect(inbox).toContainText('Action approval',{timeout:15000});
 await expect(page.getByRole('button',{name:'Open approval goal',exact:true})).toBeVisible();
 for(const target of ['/v1/goals','/v1/mission/build/plans','/v1/approvals','/v1/session/code']){
  assert.equal((await page.request.post(f.origin+target,{data:{},headers:{Origin:f.origin,'X-Panestria-CSRF':csrf}})).status(),403);
 }
 assert.equal((await page.request.get(`${f.origin}/v1/artifacts/${f.goal}`)).status(),403);
 assert.equal((await page.request.get(`${f.origin}/v1/activity/goals/${f.privateGoal}/build-progress`)).status(),404);
 const content=await page.content();for(const secret of [f.store,f.privateDescription,'PHONE_PRIVATE_CONTENT_SENTINEL'])assert(!content.includes(secret));
 // Mobile browsers can expand innerWidth to fit overflowing content. Compare
 // against the selected physical CSS viewport, not that expanded layout width.
 assert((await page.evaluate(()=>document.documentElement.scrollWidth))<=page.viewportSize().width);
 assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
 assert.equal(context.serviceWorkers().length,0);
 await page.screenshot({path:process.env.PANESTRIA_BROWSER_SCREENSHOT,fullPage:true});
 const lastObserved=await page.getByTestId('last-observed').textContent();
 await step('STOP'); // parent actually terminates the disposable workstation listener
 await expect(page.getByTestId('project-freshness')).toContainText('STALE / UNCONFIRMED',{timeout:25000});
 await expect(inbox.locator('tbody tr')).toHaveCount(0,{timeout:20000});
 await expect(evidence.getByRole('progressbar')).toHaveCount(0,{timeout:20000});
 await expect(page.getByTestId('goal-state')).toHaveText('ACTIVE');
 assert.equal(await page.getByTestId('last-observed').textContent(),lastObserved);
 await step('RESTART');
 await expect(page.getByTestId('project-freshness')).toContainText('Confirmed',{timeout:25000});
 await expect(evidence).toContainText('owner merge PENDING',{timeout:25000});
 await context.setOffline(true);
 await expect(project).toHaveCount(0);await expect(evidence).toHaveCount(0);
 await expect(page.getByRole('region',{name:'Connection'})).toContainText('This device is offline');
 await context.setOffline(false);
 await expect(page.getByTestId('project-freshness')).toContainText('Confirmed',{timeout:15000});
 // Explicit visibility fixture: no OS-background or browser suspension claim.
 await page.evaluate(()=>{Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'hidden'});document.dispatchEvent(new Event('visibilitychange'));});
 await expect(project).toHaveCount(0);await expect(inbox).toHaveCount(0);
 await page.evaluate(()=>{delete document.visibilityState;document.dispatchEvent(new Event('visibilitychange'));});
 await expect(page.getByTestId('project-freshness')).toContainText('Confirmed',{timeout:15000});
 await expect(page.getByTestId('goal-state')).toHaveText('ACTIVE');
 const events=await page.locator('[data-event-id]').evaluateAll(nodes=>nodes.map(n=>n.dataset.eventId));
 assert.equal(events.length,new Set(events).size);
 await step('REVOKE');
 await expect(project).toHaveCount(0,{timeout:20000});await expect(inbox).toHaveCount(0);
 await expect(page.getByRole('region',{name:'Goal timeline'})).toHaveCount(0);
 await expect(page.getByTestId('last-observed')).toContainText('not yet observed');
 await expect(page.getByRole('button',{name:'Pair',exact:true})).toBeVisible();
 assert.deepEqual(errors,[]);console.log('PASS');
}finally{await browser.close();}
