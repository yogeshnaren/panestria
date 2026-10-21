import {chromium,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {createInterface} from 'node:readline';
import assert from 'node:assert/strict';
const f=JSON.parse(readFileSync(process.env.PANESTRIA_BROWSER_FIXTURE,'utf8'));
const lines=createInterface({input:process.stdin})[Symbol.asyncIterator]();
async function step(name){console.log(name);assert(!(await lines.next()).done);}
const browser=await chromium.launch({headless:true});
try {
 const page=await browser.newPage(); const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(f.origin);
 await page.getByLabel('One-use pairing code from your terminal').fill(f.code);
 await page.getByRole('button',{name:'Pair',exact:true}).click();
 await page.getByRole('button',{name:`Open goal ${f.goal.slice(0,8)}`,exact:true}).click();
 await page.getByRole('button',{name:'Inspect Build evidence',exact:true}).click();
 const section=page.getByRole('region',{name:'Verified Build progress'});
 await expect(section.getByRole('progressbar')).toHaveAttribute('value','0');
 await expect(section).toContainText('release acceptance NOT_ASSESSED');
 await step('RUN');
 await expect(section.getByRole('progressbar')).toHaveAttribute('value',String(f.total),{timeout:25000});
 await expect(section).toContainText('owner merge PENDING');
 await expect(section).toContainText('Goal ACTIVE');
 await expect(section).toContainText('CONFIRMED');
 assert(!await section.textContent().then(t=>t.includes(f.privateDescription)));
 assert(!await page.content().then(t=>t.includes(f.store)));
 await page.screenshot({path:process.env.PANESTRIA_BROWSER_SCREENSHOT,fullPage:true});
 await step('CORRUPT');
 await expect(section.getByRole('progressbar')).toHaveAttribute('value','0',{timeout:25000});
 await expect(section).toContainText('UNCONFIRMED');
 await expect(section).toContainText('not confirmed');
 await expect(section).toContainText('Goal ACTIVE');
 assert.deepEqual(errors,[]);console.log('PASS');
}finally{await browser.close();}
