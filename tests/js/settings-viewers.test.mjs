// Settings → Channels & options and viewer cards: the pure part of hub/web/app.js. Run: node --test "tests/js/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const A = require('../../hub/web/app.js');
const field = (key) => A.CONFIG_FIELDS.find((f) => f.key === key);

test('every setting has a label, a one-line hint and a known kind', () => {
  assert.equal(new Set(A.CONFIG_KEYS).size, A.CONFIG_FIELDS.length);
  A.CONFIG_FIELDS.forEach((f) => {
    assert.ok(f.label && f.group, f.key);
    assert.ok(f.hint && !f.hint.includes('\n') && f.hint.length < 140, f.key);
    assert.ok(['text', 'bool', 'int', 'select'].includes(f.type), f.key);
    if (f.type === 'int') assert.ok(f.min <= f.max, f.key);
  });
  ['kick_client_secret', 'kick_client_id', 'twitch_client_id', 'obs.password', 'custom_overlays', 'browser', 'port']
    .forEach((secret) => assert.ok(!A.CONFIG_KEYS.includes(secret), secret));
});

test('typed values become what the hub takes, or say what is wrong', () => {
  assert.deepEqual(A.configValue(field('facebook'), true), { value: true });
  assert.deepEqual(A.configValue(field('facebook'), 'yes'), { value: false });     // only a ticked box is on
  assert.deepEqual(A.configValue(field('logs.keep_days'), ' 30 '), { value: 30 });
  ['0', '3651', '2.5', '-1', '1e3', '', 'ten'].forEach((bad) => assert.match(A.configValue(field('logs.keep_days'), bad).why, /whole number from 1 to 3650/, bad));
  assert.deepEqual(A.configValue(field('remote.port'), '4467'), { value: 4467 });
  assert.ok(A.configValue(field('remote.port'), '80').why);
  assert.deepEqual(A.configValue(field('twitch'), '  twitch.tv/Some_One  '), { value: 'twitch.tv/Some_One' });
  assert.match(A.configValue(field('x.title'), 'x'.repeat(121)).why, /at most 120/);
  assert.deepEqual(A.configValue(field('x.title'), 'two\nlines'), { value: 'two lines' });
  assert.deepEqual(A.configValue(field('window'), 'auto'), { value: 'auto' });
  assert.ok(A.configValue(field('window'), 'left').why);
});

test('only changed settings are sent', () => {
  const saved = { twitch: 'mine', facebook: false, 'logs.keep_days': 90 };
  assert.deepEqual(A.configChanges(saved, { twitch: 'mine', facebook: true, 'logs.keep_days': 90 }), { facebook: true });
  assert.deepEqual(A.configChanges(saved, { ...saved }), {});
  assert.deepEqual(A.configChanges(saved, { twitch: 'mine', kick_client_secret: 'x' }), {});      // unknown keys never go out
  assert.deepEqual(A.configChanges(null, { kick: 'new' }), { kick: 'new' });
});

test('a viewer card address is built from checked, encoded parts', () => {
  assert.equal(A.viewerPath({ p: 'twitch', name: 'Ann B', uid: '42' }), '/viewer?p=twitch&name=Ann%20B&uid=42');
  assert.equal(A.viewerPath({ p: 'youtube', name: 'a&b=c', uid: 'UC_x-1' }, '  big   question? '), '/viewer?p=youtube&name=a%26b%3Dc&uid=UC_x-1&q=big%20question%3F');
  assert.equal(A.viewerPath({ p: 'x', name: 'Dev', uid: '../../etc' }), '/viewer?p=x&name=Dev');      // a strange id is left out
  assert.equal(A.viewerPath({ p: 'kick', name: 'n'.repeat(300) }).length, '/viewer?p=kick&name='.length + 100);
});

test('a viewer card says what matters in plain words', () => {
  const at = () => '7:05 PM';
  assert.deepEqual(A.viewerFacts({ ok: true, first_ever: true, first_seen: 1, count: 1, past_streams: 0 }, at),
    ['First message ever in your channel', 'First message this stream at 7:05 PM', '1 message this stream']);
  assert.deepEqual(A.viewerFacts({ ok: true, first_seen: 1, count: 12, past_streams: 3 }, at),
    ['First message this stream at 7:05 PM', '12 messages this stream', 'Chatted in 3 earlier streams']);
  assert.deepEqual(A.viewerFacts({ ok: true, count: 0, past_streams: 1, truncated: true }, at),
    ['No messages this stream yet', 'Chatted in 1 earlier stream (the most recent ones)']);
  assert.deepEqual(A.viewerFacts({ ok: true, count: 2, past_streams: 0 }, at), ['2 messages this stream', 'Not in the chat history of earlier streams']);
  assert.deepEqual(A.viewerFacts(null, at), []);
  assert.deepEqual(A.viewerFacts({ ok: false }, at), []);
});

test('the card acts on the viewer\'s newest chat message', () => {
  const card = { stream: [{ id: 'e', kind: 'event' }, { id: 'b', kind: 'chat' }, { id: 'a', kind: 'chat' }] };
  assert.equal(A.viewerLatest(card).id, 'b');
  assert.equal(A.viewerLatest({ stream: [{ id: 'e', kind: 'event' }] }), null);
  assert.equal(A.viewerLatest(null), null);
  // moderation on the card is the same as on the message: nothing for X, the platform's own tools for TikTok
  const ctx = { remote: false, executor: true, twitch: 'on', kick: 'off', states: {} };
  assert.equal(A.modMenu({ p: 'twitch', kind: 'chat', name: 'ann', mid: '1', badges: [] }, ctx)[0].ok, true);
  assert.equal(A.modMenu({ p: 'x', kind: 'chat', name: 'ann', badges: [] }, ctx)[0].ok, false);
  assert.equal(A.modMenu({ p: 'kick', kind: 'chat', name: 'ann', mid: '1', badges: [] }, { ...ctx, remote: true })[1].why,
    'Connect Kick on the streaming PC (Settings) to moderate');
});
