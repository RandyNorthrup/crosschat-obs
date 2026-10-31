// Tests for the pure part of hub/web/app.js (the chat app). Run: node --test "tests/js/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const A = require('../../hub/web/app.js');
const Q = require('../../hub/web/vendor/qrcode.js');

const chat = (p, extra) => ({ id: p + '-1', p, kind: 'chat', name: 'ann', text: 'hi', badges: [], mid: '1', uid: 'u1', ...extra });
const here = { remote: false, executor: true, twitch: 'off', states: { twitch: 'on', youtube: 'on', x: 'on', kick: 'on' } };

test('replies go to the open chats that take replies, or to the one being answered', () => {
  const states = { twitch: 'on', youtube: 'waiting', x: 'on', kick: 'on' };
  assert.deepEqual(A.openPlatforms(states), ['twitch', 'x']);            // Kick can't take replies
  assert.deepEqual(A.targetsFor(states, null), ['twitch', 'x']);
  assert.deepEqual(A.targetsFor(states, { p: 'youtube' }), ['youtube']);
});

test('length limits count characters, not bytes', () => {
  assert.deepEqual(A.tooLong('😀'.repeat(140), ['x']), []);
  assert.deepEqual(A.tooLong('😀'.repeat(141), ['x', 'twitch']), ['x']);
  assert.deepEqual(A.tooLong('a'.repeat(201), ['twitch', 'youtube']), ['youtube']);
});

test('what can carry a message: Twitch on its own once connected, the rest through the chat window', () => {
  assert.equal(A.route('twitch', { executor: false, twitch: 'on' }).ok, true);
  assert.equal(A.route('youtube', { executor: false, twitch: 'on' }).ok, false);
  assert.match(A.route('youtube', { executor: false, remote: true }).why, /streaming PC/);
  assert.match(A.route('twitch', { executor: false, twitch: 'off' }).why, /Twitch connected/);
  assert.equal(A.route('kick', { executor: true }).ok, false);
  assert.equal(A.canReply(chat('youtube'), here).ok, true);
  assert.equal(A.canReply(chat('youtube'), { ...here, states: { youtube: 'off' } }).ok, false);
  assert.equal(A.canReply({ ...chat('twitch'), kind: 'event' }, here).ok, false);
});

test('moderation per platform', () => {
  const off = A.modMenu(chat('twitch'), here);
  assert.ok(off.length >= 5 && off.every((e) => !e.ok && /Connect Twitch/.test(e.why)));
  const on = A.modMenu(chat('twitch'), { ...here, twitch: 'on' });
  assert.deepEqual(on.filter((e) => e.ok).map((e) => e.action + (e.seconds || '')), ['delete', 'timeout600', 'timeout3600', 'timeout', 'ban', 'unban']);
  assert.equal(on.find((e) => e.action === 'ban').danger, true);
  assert.equal(A.modMenu(chat('twitch', { mid: '' }), { ...here, twitch: 'on' })[0].ok, false);   // no id, no delete
  const yt = A.modMenu(chat('youtube'), here);
  assert.deepEqual(yt.map((e) => e.action + (e.seconds || '')), ['delete', 'timeout300', 'ban']);
  assert.ok(A.modMenu(chat('youtube'), { ...here, executor: false }).every((e) => !e.ok));
  assert.match(A.modMenu(chat('x'), here)[0].why, /X chat/);
  assert.match(A.modMenu(chat('kick'), here)[0].why, /Kick/);
  assert.match(A.modMenu(chat('twitch', { badges: ['broadcaster'] }), { ...here, twitch: 'on' })[0].why, /you/);
});

test('quick replies are cleaned the way the hub keeps them', () => {
  assert.deepEqual(A.cleanQuick(['  GG ', 'GG', '', null, 'a\n  b']), ['GG', 'a b']);
  assert.equal(A.cleanQuick(Array.from({ length: 40 }, (_, i) => 'r' + i)).length, 30);
  assert.equal([...A.cleanQuick(['😀'.repeat(150)])[0]].length, 100);
  assert.deepEqual(A.cleanQuick('not a list'), []);
});

test('views, mentions, timers, wording', () => {
  const starred = new Set(['b']);
  assert.equal(A.inView('all', { id: 'a' }, starred), true);
  assert.equal(A.inView('questions', { id: 'a', question: true }, starred), true);
  assert.equal(A.inView('questions', { id: 'b' }, starred), false);
  assert.equal(A.inView('starred', { id: 'b' }, starred), true);
  assert.equal(A.mention({ name: 'Sam Ortiz' }), '@Sam Ortiz ');
  assert.equal(A.mention({ name: 'Lena', handle: 'lenapark' }), '@lenapark ');
  const now = 1793462400000;                                          // 2026-10-31, in milliseconds
  assert.equal(A.secondsLeft(now / 1000 + 90, now), 90);              // Unix seconds
  assert.equal(A.secondsLeft(now + 5000, now), 5);                    // milliseconds
  assert.equal(A.secondsLeft(now / 1000 - 10, now), 0);               // already over
  assert.equal(A.duration(600), '10 min');
  assert.equal(A.duration(3600), '1 h');
  assert.equal(A.describe('timeout', 'bob', 600), 'timed out bob for 10 min');
});

test('name colours stay readable on each theme', () => {
  assert.equal(A.readable('', false), '');
  assert.equal(A.readable('#ffffff', false), 'rgb(255,255,255)');      // light on dark: kept
  assert.notEqual(A.readable('#000080', false), 'rgb(0,0,128)');       // dark on dark: lifted
  assert.notEqual(A.readable('#ffff00', true), 'rgb(255,255,0)');      // yellow on light: darkened
});

test('Twitch emotes are cut out by code point', () => {
  assert.deepEqual(A.pieces('hi Kappa', '25:3-7'), [{ text: 'hi ' }, { emote: '25', alt: 'Kappa' }]);
  assert.deepEqual(A.pieces('😀 Kappa', '25:2-6'), [{ text: '😀 ' }, { emote: '25', alt: 'Kappa' }]);
  assert.deepEqual(A.pieces('plain', ''), [{ text: 'plain' }]);
  assert.deepEqual(A.pieces('x', '<bad>:0-0'), [{ text: 'x' }]);         // ids are word characters only
});

test('the vendored QR encoder makes a code for a pairing address', () => {
  const code = Q(0, 'M');
  code.addData('http://192.168.1.20:4467/pair?code=482913');
  code.make();
  assert.ok(code.getModuleCount() >= 25);
  assert.equal(typeof code.isDark(0, 0), 'boolean');
});
