import type { components } from './schema';
export type Activity = components['schemas']['ProjectActivity'];
export type Timeline = components['schemas']['ActivityTimeline'];
export type Event = components['schemas']['ActivityEvent'];
export type Scope = 'activity'|'ask'|'build';
// A 401/403 refusal. Only the server's fixed code is kept (for example
// session_scope_denied: paired, but for another scope); the body is never shown.
export class Denied extends Error {
  constructor(readonly code = 'denied') {super('Pairing required or access denied.');}
}
export class NotCommitted extends Error {}
const decimal = /^(0|[1-9][0-9]{0,18})$/;
export function cursor(value: unknown): value is string {
  return typeof value === 'string' && decimal.test(value) && BigInt(value) <= 9223372036854775807n;
}
export function event(value: unknown): value is Event {
  if (!value || typeof value !== 'object') return false;
  const x = value as Event;
  return cursor(x.seq) && typeof x.id === 'string' && /^[0-9a-f-]{36}$/.test(x.id) &&
    typeof x.kind === 'string' && x.kind.length <= 128 && typeof x.privacy_label === 'string';
}
export async function json<T>(path: string, signal: AbortSignal, body?: object, csrf?: string, timeoutMs = 8000): Promise<T> {
  const response = await fetch(path, {method: body ? 'POST' : 'GET', credentials: 'same-origin',
    mode: 'same-origin', redirect: 'error', cache: 'no-store', signal: AbortSignal.any([signal,AbortSignal.timeout(timeoutMs)]), headers: body ? {'Content-Type': 'application/json',
      ...(csrf ? {'X-Panestria-CSRF': csrf} : {})} : {}, body: body ? JSON.stringify(body) : undefined});
  if (response.status === 401 || response.status === 403) throw await denial(response);
  if (!response.ok) {
    if(body && /^\/v1\/mission\/build\/plans(?:\/[0-9a-f-]{36}\/accept)?$/.test(path) &&
       [409,422].includes(response.status) && response.headers.get('X-Panestria-Mutation')==='NOT_COMMITTED')
      throw new NotCommitted('This request was rejected before commit.');
    throw new Error('Server unavailable or request denied.');
  }
  return JSON.parse(await bounded(response, 262144)) as T;
}
// Bounded response retention; error messages never echo bodies, URLs or private data.
async function bounded(response: Response, limit: number): Promise<string> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error('Missing response.');
  let size = 0, text = '';
  const decoder = new TextDecoder();
  try {
    for (;;) { const {value, done} = await reader.read(); if (done) break;
      size += value.length; if (size > limit) throw new Error('Response exceeds local view limit.');
      text += decoder.decode(value, {stream: true});
    }
    return text + decoder.decode();
  } finally { await reader.cancel(); }
}
async function denial(response: Response): Promise<Denied> {
  try {
    const code: unknown = JSON.parse(await bounded(response, 4096))?.code;
    return new Denied(typeof code === 'string' && /^[a-z_]{1,64}$/.test(code) ? code : undefined);
  } catch { return new Denied(); }
}
export function validateTimeline(value: Timeline, goal: string, scope: Activity): Timeline {
  if (value.owner_id !== scope.owner_id || value.project_id !== scope.project_id ||
      value.snapshot?.goal_id !== goal || value.view_authority !== 'READ_ONLY_METADATA' ||
      value.acceptance_authority !== 'NONE' || !cursor(value.next_cursor) || !cursor(value.snapshot.cursor) ||
      !Array.isArray(value.events) || value.events.length > 50 || !value.events.every(event) ||
      !Array.isArray(value.snapshot.tasks) || typeof value.snapshot.status !== 'string' ||
      typeof value.resync !== 'boolean') throw new Error('Unconfirmed timeline response.');
  return value;
}
export function mergeEvents(prior: Event[], page: Timeline): Event[] {
  const entries = new Map((page.resync ? [] : prior).map(e => [e.id, e]));
  for (const item of page.events) entries.set(item.id, item);
  const bySequence = new Map<string, Event>();
  for (const item of entries.values()) {
    const same = bySequence.get(item.seq);
    if (same && same.id !== item.id) throw new Error('Ambiguous timeline sequence.');
    bySequence.set(item.seq, item);
  }
  return [...bySequence.values()].sort((a,b) => BigInt(a.seq) < BigInt(b.seq) ? -1 : 1).slice(-200);
}
// SSE is a change notification. Only a fresh canonical JSON snapshot advances the
// display/cursor. Reconnect/backfill uses that cursor, never optimistic events.
export async function waitForChange(path: string, after: string, signal: AbortSignal): Promise<void> {
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), 10000);
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  try {
    const response = await fetch(`${path}?after=${after}`, {credentials: 'same-origin', cache: 'no-store',
      headers: {Accept: 'text/event-stream'}, signal: AbortSignal.any([signal, timeout.signal])});
    if (response.status === 401 || response.status === 403) throw await denial(response);
    if (!response.ok || !response.headers.get('content-type')?.startsWith('text/event-stream'))
      throw new Error('Event connection unavailable.');
    reader = response.body?.getReader(); if (!reader) throw new Error('Missing event connection.');
    const decoder = new TextDecoder(); let pending = '';
    for (;;) {
      const {value, done} = await reader.read(); if (done) return;
      pending += decoder.decode(value, {stream:true});
      if (pending.length > 131072) throw new Error('Event exceeds local view limit.');
      let end: number;
      while ((end = pending.indexOf('\n\n')) >= 0) {
        const frame = pending.slice(0,end); pending = pending.slice(end+2);
        if (frame.includes('event: error')) {
          const refused = /"code":"?(unauthorized|origin_denied)/.exec(frame.replaceAll(' ',''));
          if (refused) throw new Denied(refused[1]);
          throw new Error('Event connection unavailable.');
        }
        if (/^event: (task-event|resync)$/m.test(frame)) return;
      }
    }
  } catch (error) { if (!timeout.signal.aborted || signal.aborted) throw error;
  } finally { clearTimeout(timer); await reader?.cancel().catch(() => {}); }
}
