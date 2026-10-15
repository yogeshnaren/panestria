"use strict";
const byId = (id) => document.getElementById(id);
const ui = Object.fromEntries(["pair-form", "pair-code", "pair-button", "logout", "connection", "scope", "ask-form", "question", "send", "cancel", "status", "result", "answer", "receipt", "sources"].map((id) => [id, byId(id)]));
let csrf = null;
let project = null;
let active = null;

function controls() {
  ui.question.disabled = !project || Boolean(active);
  ui.send.disabled = !project || Boolean(active);
  ui.cancel.disabled = !active;
  ui.logout.disabled = !csrf;
}
function clearAnswer() {
  ui.answer.textContent = "";
  ui.receipt.textContent = "";
  ui.sources.replaceChildren();
  ui.result.hidden = true;
}
function safeCode(body) {
  return typeof body?.code === "string" && /^[a-z0-9_]{1,80}$/.test(body.code) ? body.code : "local_api_unavailable";
}
async function api(path, {body, signal} = {}) {
  const headers = body === undefined ? {} : {"Content-Type": "application/json"};
  if (csrf) headers["X-Panestria-CSRF"] = csrf;
  const response = await fetch(path, {method: body === undefined ? "GET" : "POST", headers,
    body: body === undefined ? undefined : JSON.stringify(body), credentials: "same-origin",
    mode: "same-origin", redirect: "error", cache: "no-store", signal: signal || AbortSignal.timeout(8000)});
  const text = await response.text();
  if (text.length > 1024 * 1024) throw new Error("response_size_limit");
  const result = JSON.parse(text);
  if (!response.ok) throw new Error(safeCode(result));
  return result;
}
function reason(error) {
  return error instanceof Error && /^[a-z0-9_]{1,80}$/.test(error.message) ? error.message : "local_connection_unavailable";
}

ui["pair-form"].addEventListener("submit", async (event) => {
  event.preventDefault();
  const code = ui["pair-code"].value.trim().toUpperCase();
  if (!/^[0-9A-F]{8}$/.test(code) || active) return;
  ui["pair-button"].disabled = true;
  try {
    const paired = await api("/v1/session/pair", {body: {code}});
    csrf = paired.csrf_token;
    const status = await api("/v1/local/status");
    if (!/^[0-9a-f-]{36}$/.test(status.project_id) || status.profiles !== "DISABLED") throw new Error("local_scope_unavailable");
    project = status.project_id;
    ui["pair-code"].value = "";
    ui.scope.textContent = `Project ${project}. Local read-only scope; runtime certification is pending.`;
    ui.connection.textContent = "Connected to this workstation. Reload requires a fresh code.";
    ui.status.textContent = "Connected. Ask uses the local model and this project’s approved memory.";
    ui.question.disabled = false;
    ui.question.focus();
  } catch (error) {
    project = null;
    ui.connection.textContent = `Connection failed: ${reason(error)}. Issue a fresh terminal code and retry.`;
  } finally {
    ui["pair-button"].disabled = false;
    controls();
  }
});

ui["ask-form"].addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = ui.question.value.trim();
  if (!project || active || !question) return;
  if (new TextEncoder().encode(question).length > 4096) {
    ui.status.textContent = "This question exceeds the 4096-byte input limit.";
    return;
  }
  clearAnswer();
  const request = {id: crypto.randomUUID(), controller: new AbortController(), cancelled: false};
  active = request;
  const deadline = setTimeout(() => request.controller.abort(), 65000);
  controls();
  ui.status.textContent = "Working locally… You can cancel this request.";
  try {
    const answer = await api("/v1/ask", {body: {request_id: request.id, project_id: project, question,
      privacy_label: "RESTRICTED", offline: true, retain_response: false, deadline_seconds: 60.0}, signal: request.controller.signal});
    if (request.cancelled) return;
    ui.result.hidden = false;
    ui.answer.textContent = answer.text || "No answer text retained. Only the receipt is available.";
    ui.receipt.textContent = `Request ${request.id} · ${answer.state} · ${answer.privacy_label} · offline · response not retained`;
    for (const source of answer.sources || []) {
      const item = document.createElement("li");
      item.textContent = `Source ${source.source_id} · revision ${source.revision_id}`;
      ui.sources.append(item);
    }
    if (!ui.sources.children.length) {
      const item = document.createElement("li"); item.textContent = "No stored project sources used."; ui.sources.append(item);
    }
    ui.status.textContent = `${answer.state}. This is the current response; no conversation history is saved by this page.`;
  } catch (error) {
    if (!request.cancelled) ui.status.textContent = `Request stopped: ${reason(error)}. Receipt ID: ${request.id}. No retry or cloud fallback was started.`;
  } finally {
    clearTimeout(deadline);
    if (active === request) active = null;
    controls();
  }
});

async function cancel() {
  const request = active;
  if (!request) return;
  request.cancelled = true;
  ui.cancel.disabled = true;
  try {
    const receipt = await api(`/v1/ask/${request.id}/cancel`, {body: {}});
    if (active === request || !active) ui.status.textContent = `Request ${request.id} · ${receipt.state}. Its durable receipt is authoritative.`;
  } catch (error) {
    if (active === request || !active) ui.status.textContent = `Cancellation could not be confirmed: ${reason(error)}. Request ${request.id}; check its receipt before retrying.`;
  } finally {
    request.controller.abort();
  }
}
ui.cancel.addEventListener("click", cancel);
ui.logout.addEventListener("click", async () => {
  ui.logout.disabled = true;
  if (active) await cancel();
  ui.question.value = "";
  clearAnswer();
  project = null;
  try {
    await api("/v1/session/logout", {body: {}});
    csrf = null;
    ui.connection.textContent = "Disconnected. The session was revoked and current text cleared.";
    ui.status.textContent = "Disconnected. Pair again to ask.";
  } catch (error) {
    ui.connection.textContent = `Text cleared; session revocation failed: ${reason(error)}. Retry Disconnect.`;
    ui.status.textContent = "Text cleared. Retry Disconnect to revoke the session.";
  }
  ui.scope.textContent = "No project loaded.";
  controls();
});
window.addEventListener("pagehide", () => {
  if (active) active.controller.abort();
  csrf = null;
  project = null;
  ui.question.value = "";
  ui["pair-code"].value = "";
  clearAnswer();
  controls();
});
