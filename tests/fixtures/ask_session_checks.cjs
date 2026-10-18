// Execute the packaged script with deterministic DOM/HTTP seams, not a browser certificate.
const assert = require("assert/strict");
const vm = require("vm");
const fs = require("fs");
const { webcrypto } = require("crypto");
const project = "12345678-1234-1234-1234-123456789abc";
function harness() {
  const nodes = new Map(), listeners = new Map(), timers = new Map(), pending = [];
  let counter = 0;
  function element() {
    return { value: "", textContent: "", children: [], hidden: false, disabled: false, listeners: {},
      replaceChildren() { this.children = []; }, append(child) { this.children.push(child); }, focus() {},
      addEventListener(name, callback) { this.listeners[name] = callback; } };
  }
  const context = vm.createContext({
    document: { getElementById(id) { if (!nodes.has(id)) nodes.set(id, element()); return nodes.get(id); }, createElement: element },
    window: { addEventListener(name, callback) { listeners.set(name, callback); } },
    crypto: webcrypto, TextEncoder, AbortController, AbortSignal: { timeout: () => new AbortController().signal },
    setTimeout(callback, delay) { const id = ++counter; timers.set(id, { callback, delay }); return id; },
    clearTimeout(id) { timers.delete(id); },
    fetch(path, options) { return new Promise((resolve, reject) => pending.push({path, options, resolve, reject})); }
  });
  vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), context);
  const node = id => nodes.get(id);
  const submit = id => node(id).listeners.submit({preventDefault() {}});
  const reply = (status, body, raw) => {
    assert(pending.length, "expected HTTP request");
    const request = pending.shift();
    request.resolve({status, ok: status >= 200 && status < 300, text: async () => raw === undefined ? JSON.stringify(body) : raw});
    return request;
  };
  const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
  async function pair() {
    node("pair-code").value = "ABCD1234";
    const job = submit("pair-form");
    reply(200, {csrf_token: "synthetic-csrf"}); await flush();
    reply(200, {project_id: project, profiles: "DISABLED"}); await job;
    assert.equal(node("send").disabled, false);
  }
  async function answer() {
    node("question").value = "PUBLIC fixture";
    const job = submit("ask-form");
    reply(200, {text: "PRIVATE_ANSWER_SENTINEL", state: "COMPLETED", privacy_label: "RESTRICTED", sources: []});
    await job; assert.equal(node("answer").textContent, "PRIVATE_ANSWER_SENTINEL");
  }
  function erased() {
    assert.equal(node("answer").textContent, ""); assert.equal(node("question").value, "");
    assert.equal(node("receipt").textContent, ""); assert.equal(node("sources").children.length, 0);
    assert.equal(node("send").disabled, true); assert.equal(node("result").hidden, true);
  }
  async function checkSession() {
    const item = [...timers.entries()].find(([, t]) => t.delay === 5000);
    assert(item, "paired page must monitor session"); timers.delete(item[0]);
    const job = item[1].callback(); await flush(); return {job};
  }
  return {node, listeners, timers, pending, submit, reply, flush, pair, answer, erased, checkSession};
}
async function run() {
  for (const status of [401, 403]) {
    const h = harness(); await h.pair(); await h.answer();
    const {job} = await h.checkSession(); h.reply(status, null, "not-json"); await job;
    h.erased(); assert.equal(h.timers.size, 0);
  }
  {
    const h = harness(); await h.pair(); h.node("question").value = "PRIVATE_QUESTION";
    const answer = h.submit("ask-form"), request = h.pending.shift();
    h.listeners.get("pagehide")(); h.erased();
    // Simulate a response already buffered when abort/pagehide occurred.
    request.resolve({status:200,ok:true,text:async () => JSON.stringify({text:"LATE_PRIVATE",sources:[]})});
    await answer; h.erased(); assert.equal(h.timers.size, 0);
  }
  {
    const h = harness(); h.node("pair-code").value = "ABCD1234";
    const pairing = h.submit("pair-form"); h.listeners.get("pagehide")();
    h.reply(200, {csrf_token:"synthetic-csrf"}); await pairing;
    h.erased(); assert.equal(h.pending.length, 0);
  }
  {
    const h = harness(); await h.pair(); await h.answer();
    const logout = h.node("logout").listeners.click(); h.erased();
    h.reply(500, {code:"unavailable"}); await logout; h.erased();
    assert.equal(h.node("logout").disabled, false, "unconfirmed revocation remains retryable");
    const retry = h.node("logout").listeners.click(); h.reply(200, {}); await retry;
    assert.equal(h.node("logout").disabled, true);
  }
  {
    const h = harness(); await h.pair(); await h.answer();
    const logout = h.node("logout").listeners.click();
    h.listeners.get("pagehide")(); h.reply(500, {code:"unavailable"}); await logout;
    h.erased(); assert.equal(h.node("logout").disabled, true, "late logout cannot restore a pagehide retry handle");
  }
  {
    const h = harness(); await h.pair();
    const {job: oldCheck} = await h.checkSession(), oldRequest = h.pending.shift();
    await h.pair();
    oldRequest.resolve({status:401,ok:false,text:async () => JSON.stringify({code:"unauthorized"})});
    await oldCheck; assert.equal(h.node("send").disabled, false, "old denial cannot erase a new paired scope");
  }
  process.stdout.write("7 session scenarios passed\n");
}
run().catch(error => { process.stderr.write(error.stack + "\n"); process.exitCode = 1; });
