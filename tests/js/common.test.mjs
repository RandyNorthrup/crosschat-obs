// Tests for extension/common.js: what the page scripts share. Run: node --test "tests/js/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadExtension } from './extension-files.mjs';

const C = loadExtension('common.js').CrossChatCommon;

test('waiting goes by the clock and returns what was found', async () => {
  let n = 0;
  assert.equal(await C.waitFor(() => (++n >= 2 ? 'menu' : null), 2000), 'menu');
  const started = Date.now();
  assert.equal(await C.waitFor(() => null, 300), null);
  assert.ok(Date.now() - started >= 300);
});

test('a wait does not run long when its timers are late, as in a background tab', async () => {
  // Counting 25 sleeps of 200 ms is 5 seconds only if each sleep is on time; a late timer stretches it, by a minute a sleep in a throttled tab.
  const realDateNow = Date.now, realSetTimeout = globalThis.setTimeout;
  let now = 1000, sleeps = 0;
  Date.now = () => now;
  globalThis.setTimeout = (fn) => { sleeps += 1; now += 1000; return realSetTimeout(fn, 0); };   // each sleep takes a whole second
  try {
    assert.equal(await C.waitFor(() => null, 5000, 200), null);
  } finally {
    Date.now = realDateNow; globalThis.setTimeout = realSetTimeout;
  }
  assert.ok(sleeps <= 6, 'stopped by the clock, after ' + sleeps + ' sleeps');
});

test('it looks once more after the time is up, so a late timer never misses what came meanwhile', async () => {
  const realDateNow = Date.now, realSetTimeout = globalThis.setTimeout;
  let now = 0, looks = 0;
  Date.now = () => now;
  globalThis.setTimeout = (fn) => { now += 1000; return realSetTimeout(fn, 0); };            // the one sleep overruns the wait
  try {
    assert.equal(await C.waitFor(() => (++looks === 2 ? 'there' : null), 500, 100), 'there');
  } finally {
    Date.now = realDateNow; globalThis.setTimeout = realSetTimeout;
  }
});

test('ask() answers null when the extension can not', async () => {
  const realChrome = globalThis.chrome;
  try {
    globalThis.chrome = { runtime: { lastError: { message: 'no' }, sendMessage: (m, r) => r('ignored') } };
    assert.equal(await C.ask('tt-check'), null);
    globalThis.chrome = undefined;                             // the extension was updated under the page
    assert.equal(await C.ask('tt-check'), null);
    let message;
    globalThis.chrome = { runtime: { lastError: null, sendMessage: (m, r) => { message = m; r({ reached: true }); } } };
    assert.deepEqual(await C.ask('tt-feed', { page: 'x' }), { reached: true });
    assert.deepEqual(message, { type: 'tt-feed', data: { page: 'x' } });
  } finally {
    globalThis.chrome = realChrome;
  }
});

test('hash, clean', () => {
  assert.equal(C.hash('sunny\nhello'), C.hash('sunny\nhello'));
  assert.notEqual(C.hash('a'), C.hash('b'));
  assert.equal(C.clean('  two   words\n'), 'two words');
  assert.equal(C.clean(null), '');
});

// sendLines with a hub that says yes (or, from `lost` on, nothing).
async function sent(lines, fields, lost = Infinity) {
  const requests = [], took = [];
  const realChrome = globalThis.chrome;
  globalThis.chrome = { runtime: { lastError: null, sendMessage: (m, r) => {
    requests.push(m);
    r(requests.length > lost ? null : { reached: true, data: { mine: true } });
  } } };
  try {
    await C.sendLines('fb-feed', fields || { viewers: '12' }, lines, (l) => took.push(l));
  } finally {
    globalThis.chrome = realChrome;
  }
  return { requests, took, rows: requests.map((m) => JSON.parse(m.data.lines)) };
}

test('no request carries more lines than the hub reads, on any platform', async () => {
  const lines = Array.from({ length: 120 }, (_, i) => ({ node: { i }, id: 'n' + i, name: 'a', text: 'hi' }));
  const { rows, took } = await sent(lines);
  assert.ok(rows.every((r) => r.length <= C.BATCH_MOST), 'at most ' + C.BATCH_MOST + ' a request');
  assert.equal(rows.flat().length, 120);
  assert.equal(took.length, 120);
});

test('a burst of emoji is split so each request stays small, and only what goes to the hub goes', async () => {
  const lines = Array.from({ length: 30 }, (_, i) => ({ node: { i }, sig: 'secret', id: 'n' + i, name: 'a', text: '🎉'.repeat(140) }));
  const { requests, rows } = await sent(lines);
  assert.ok(requests.length > 1);
  assert.ok(requests.every((m) => encodeURIComponent(m.data.lines).length < 10000));
  assert.deepEqual(Object.keys(rows[0][0]), ['id', 'name', 'text']);
});

test('the viewer count goes even with no new lines', async () => {
  const { requests } = await sent([], { page: 'me', viewers: '7' });
  assert.deepEqual(requests, [{ type: 'fb-feed', data: { page: 'me', viewers: '7', lines: '[]' } }]);
});

test('lines the hub did not take stay for next time', async () => {
  const lines = Array.from({ length: 60 }, (_, i) => ({ node: { i }, id: 'n' + i, name: 'a', text: 'hi' }));
  const { took, requests } = await sent(lines, undefined, 1);
  assert.equal(requests.length, 2);
  assert.equal(took.length, 50);
});
