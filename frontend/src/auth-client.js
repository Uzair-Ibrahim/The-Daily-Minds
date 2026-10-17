
const storageKey = 'daily-mind-auth-session';
function read(key) { try { return localStorage.getItem(key); } catch { return null; } }
function write(key, value) { try { localStorage.setItem(key, value); } catch {} }
export const guestID = read('daily-mind-reader') || crypto.randomUUID();
write('daily-mind-reader', guestID);
let token = null;
let scope = 'guest';
export function useGuest() { token = null; scope = 'guest'; write('daily-mind-auth-mode', 'guest'); }
export function useAccount(session) { token = session.access_token; scope = 'account:' + session.user.id; write('daily-mind-auth-mode', 'account'); }
export function accountExpected() { return read('daily-mind-auth-mode') === 'account'; }
export function requestHeaders(expectedScope = scope) {
  if (expectedScope !== scope) throw new Error('Your reading room changed. Reopen the current view to continue.');
  return token ? { Authorization: `Bearer ${token}` } : { 'X-Reader-ID': guestID };
}
export async function boundedFetch(url, options = {}) {
  return fetch(url, { ...options, signal: AbortSignal.any([options.signal || new AbortController().signal, AbortSignal.timeout(8000)]) });
}
export async function authDeadline(operation) {
  let timer;
  try {
    return await Promise.race([operation, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error('Account service timed out. Please retry or continue as guest.')), 12000);
    })]);
  } finally { clearTimeout(timer); }
}
export async function authClient(config) {
  const { createClient } = await import('@supabase/supabase-js');
  return createClient(config.url, config.publishable_key, {
    global: { fetch: boundedFetch },
    auth: { storageKey, persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
  });
}
export function clearSession() {
  useGuest();
  try { localStorage.removeItem(storageKey); localStorage.removeItem(storageKey + '-code-verifier'); } catch {}
}
