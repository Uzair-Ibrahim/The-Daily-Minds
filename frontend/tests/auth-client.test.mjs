import assert from 'node:assert/strict';
import test from 'node:test';

const storage = new Map();
globalThis.localStorage = {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
  removeItem: key => storage.delete(key),
};
const auth = await import('../src/auth-client.js');
const account = (id, token) => ({ user: { id }, access_token: token });

test('in-flight work from another account cannot acquire the new account credentials', () => {
  auth.useAccount(account('a', 'TEST_ONLY_A'));
  assert.equal(auth.requestHeaders('account:a').Authorization, 'Bearer TEST_ONLY_A');
  auth.useAccount(account('b', 'TEST_ONLY_B'));
  assert.throws(() => auth.requestHeaders('account:a'), /reading room changed/);
  assert.throws(() => auth.requestHeaders('guest'), /reading room changed/);
  assert.equal(auth.requestHeaders('account:b').Authorization, 'Bearer TEST_ONLY_B');
});

test('refresh updates tokens without changing scope; signout never reuses account headers', () => {
  auth.useAccount(account('a', 'TEST_ONLY_OLD'));
  auth.useAccount(account('a', 'TEST_ONLY_REFRESHED'));
  assert.equal(auth.requestHeaders('account:a').Authorization, 'Bearer TEST_ONLY_REFRESHED');
  auth.useGuest();
  assert.throws(() => auth.requestHeaders('account:a'), /reading room changed/);
  assert.deepEqual(auth.requestHeaders('guest'), { 'X-Reader-ID': auth.guestID });
});

test('local cleanup removes persistent sessions and keeps the original guest profile', () => {
  storage.set('daily-mind-auth-session', 'TEST_ONLY_SESSION');
  storage.set('daily-mind-auth-session-code-verifier', 'TEST_ONLY_VERIFIER');
  auth.clearSession();
  assert.equal(storage.get('daily-mind-auth-session'), undefined);
  assert.equal(storage.get('daily-mind-auth-session-code-verifier'), undefined);
  assert.equal(storage.get('daily-mind-reader'), auth.guestID);
  assert.equal(auth.accountExpected(), false);
});

test('SDK operations have a UI deadline even if the underlying operation stalls', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const operation = auth.authDeadline(new Promise(() => {}));
  const rejected = assert.rejects(operation, /timed out/);
  t.mock.timers.tick(12000);
  await rejected;
});
