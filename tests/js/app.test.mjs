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
  assert.deepEqual(A.openPlatforms(states), ['twitch', 'x']);            // Kick takes replies only once connected
  assert.deepEqual(A.openPlatforms(states, 'pending'), ['twitch', 'x']);
  assert.deepEqual(A.openPlatforms(states, 'on'), ['twitch', 'x', 'kick']);
  assert.deepEqual(A.targetsFor(states, null), ['twitch', 'x']);
  assert.deepEqual(A.targetsFor(states, null, 'on'), ['twitch', 'x', 'kick']);
  assert.deepEqual(A.targetsFor(states, { p: 'youtube' }), ['youtube']);
  assert.deepEqual(A.tooLong('a'.repeat(501), ['kick']), ['kick']);
});

test('length limits count characters, not bytes', () => {
  assert.deepEqual(A.tooLong('😀'.repeat(140), ['x']), []);
  assert.deepEqual(A.tooLong('😀'.repeat(141), ['x', 'twitch']), ['x']);
  assert.deepEqual(A.tooLong('a'.repeat(201), ['twitch', 'youtube']), ['youtube']);
});

test('what can carry a message: Twitch and Kick once connected, the rest through the chat window', () => {
  assert.equal(A.route('twitch', { executor: false, twitch: 'on' }).ok, true);
  assert.equal(A.route('youtube', { executor: false, twitch: 'on' }).ok, false);
  assert.match(A.route('youtube', { executor: false, remote: true }).why, /streaming PC/);
  assert.equal(A.route('twitch', { executor: false, twitch: 'off' }).why, 'Connect Twitch in Settings to reply on Twitch');
  assert.equal(A.route('twitch', { executor: true, twitch: 'off' }).ok, false);   // no more replies through the extension
  assert.equal(A.route('kick', { executor: true }).ok, false);
  assert.equal(A.route('kick', { executor: false, kick: 'on' }).ok, true);
  assert.match(A.route('kick', { remote: true }).why, /Connect Kick in Settings on the streaming PC/);
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
  assert.ok(A.modMenu(chat('kick'), here).every((e) => !e.ok && e.why === 'Connect Kick in Settings to moderate'));
  const kick = A.modMenu(chat('kick'), { ...here, kick: 'on' });
  assert.deepEqual(kick.filter((e) => e.ok).map((e) => e.action + (e.seconds || '')), ['delete', 'timeout600', 'timeout3600', 'timeout', 'ban', 'unban']);
  assert.match(A.modMenu(chat('twitch', { badges: ['broadcaster'] }), { ...here, twitch: 'on' })[0].why, /you/);
  // Facebook (delete only) and Rumble (delete, 5-minute mute, mute for the stream, mute forever) go through their pages.
  assert.deepEqual(A.modMenu(chat('facebook'), here).map((e) => e.action + ':' + e.ok), ['delete:true']);
  const rumble = A.modMenu(chat('rumble'), here);
  assert.deepEqual(rumble.map((e) => e.action + (e.seconds || '')), ['delete', 'timeout300', 'mute', 'ban']);
  assert.equal(rumble.find((e) => e.action === 'ban').danger, true);
  assert.ok(A.modMenu(chat('rumble'), { ...here, executor: false }).every((e) => !e.ok && /window/.test(e.why)));
  assert.ok(A.modMenu(chat('facebook', { mid: '' }), here).every((e) => !e.ok));
  assert.equal(A.describe('mute', 'Bo', 0), 'muted Bo for this stream');
});

test('custom timeouts fit each platform', () => {
  assert.equal(A.timeoutSeconds('kick', 1.2), 120);                    // Kick: whole minutes, rounded up
  assert.equal(A.timeoutSeconds('kick', 0), 60);
  assert.equal(A.timeoutSeconds('kick', 99999), 604800);               // at most 7 days
  assert.equal(A.timeoutSeconds('twitch', 1.5), 90);
  assert.equal(A.timeoutSeconds('twitch', 99999), 1209600);            // at most 14 days
});

test('text-to-speech settings are filled in and kept in range', () => {
  const d = A.ttsSettings(null);
  assert.deepEqual(d, { enabled: false, read: 'all', command: '!tts', names: true, max_chars: 200, skip_links: true, platforms: 'all', voice: '', rate: 1, volume: 1 });
  const s = A.ttsSettings({ enabled: true, read: 'nope', max_chars: 9000, rate: '0.1', volume: -3, platforms: ['kick', 'x', 'tiktok', 'myspace'], command: '  ' });
  assert.equal(s.read, 'all'); assert.equal(s.max_chars, 500); assert.equal(s.rate, 0.5); assert.equal(s.volume, 0);
  assert.deepEqual(s.platforms, ['kick', 'x', 'tiktok']); assert.equal(s.command, '!tts');
  assert.equal(A.ttsSettings({ platforms: ['twitch', 'youtube', 'kick', 'x', 'tiktok', 'facebook', 'instagram', 'rumble'] }).platforms, 'all');
  assert.deepEqual(A.ttsSettings({ platforms: ['twitch', 'youtube', 'kick', 'x', 'tiktok', 'facebook', 'rumble'] }).platforms,
                   ['twitch', 'youtube', 'kick', 'x', 'tiktok', 'facebook', 'rumble']);
});

const V = (name, localService, lang = 'en-US') => ({ name, localService, lang });
const VOICES = [V('Microsoft Aria Online (Natural) - English (United States)', false), V('Google Deutsch', false, 'de-DE'),
                V('Microsoft Hedda - German (Germany)', true, 'de-DE'), V('Microsoft Zira - English (United States)', true), V('Google US English', false)];

test('voices: on this PC first, online ones apart and never picked on their own', () => {
  const g = A.voiceGroups(VOICES, 'en-US');
  assert.deepEqual(g.local.map((v) => v.name), ['Microsoft Zira - English (United States)', 'Microsoft Hedda - German (Germany)']);
  assert.deepEqual(g.online.map((v) => v.name), ['Microsoft Aria Online (Natural) - English (United States)', 'Google US English', 'Google Deutsch']);
  assert.equal(A.pickVoice(VOICES, '', 'en-US').name, 'Microsoft Zira - English (United States)');            // default: the first on this PC
  assert.equal(A.pickVoice(VOICES, 'Google US English', 'en-US').name, 'Google US English');                // exactly the saved one
  assert.equal(A.pickVoice(VOICES, 'A voice from another PC', 'en-US').localService, true);                 // missing: a local one, never online
  assert.equal(A.pickVoice(VOICES.filter((v) => !v.localService), '', 'en-US'), null);                      // no local voice: none at all
  assert.equal(A.voiceMaker(VOICES[1]), 'Google');
  assert.equal(A.voiceMaker(VOICES[0]), 'Microsoft');
  assert.equal(A.onlineVoice(VOICES[3]), false);
});

test('the read-aloud queue says one line at a time, in order', () => {
  const q = A.speech(3);
  const a = { id: 'a', text: 'one' }, b = { id: 'b', text: 'two' }, c = { id: 'c', text: 'three' };
  assert.equal(q.add(a), a);                                          // nothing playing: say it now
  assert.equal(q.add(b), null);                                       // waits its turn
  assert.equal(q.add({ id: 'b', text: 'two again' }), null);          // already waiting
  assert.equal(q.add({ id: 'e', text: '   ' }), null);                // nothing to say
  q.add(c);
  assert.equal(q.waiting, 2);
  assert.equal(q.done(b), null);                                      // not the one playing: ignored
  assert.equal(q.done(a), b);
  assert.equal(q.done(b), c);
  assert.equal(q.done(c), null);
  assert.equal(q.current, null);
  q.add(a); q.add(b);
  assert.equal(q.stop(), true);
  assert.equal(q.done(a), null);                                      // a stopped line ending later changes nothing
  assert.equal(q.add(c), c);
  const full = A.speech(2); full.add(a); ['1', '2', '3'].forEach((id) => full.add({ id, text: id }));
  assert.equal(full.waiting, 2);                                      // too many waiting: the oldest is dropped
});

test('filter lists, connection health, chat logs', () => {
  assert.deepEqual(A.cleanList([' Spoiler ', 'spoiler', '', null, 'a'.repeat(80)]), ['Spoiler', 'a'.repeat(50)]);
  assert.equal(A.cleanList(Array.from({ length: 250 }, (_, i) => 'w' + i)).length, 200);
  assert.deepEqual(A.filterSettings({ words: ['x'], bots: 'yes' }), { words: ['x'], users: [], hide_commands: false, bots: false, joins: false });
  assert.equal(A.filterSettings({ joins: true }).joins, true);
  assert.equal(A.filterSettings({ joins: 'on' }).joins, false);
  const now = 1793462400000;
  assert.equal(A.health({ since: now - 72 * 60000, last: now - 8000, reconnects: 2 }, now), 'connected 1 h 12 m · last message 8 s ago · 2 reconnects');
  assert.equal(A.health({ since: (now - 45000) / 1000, last: 0, reconnects: 1 }, now), 'connected 45 s · no messages yet · 1 reconnect');
  assert.equal(A.health({ since: 0, last: 0, reconnects: 0 }, now), 'not connected');
  assert.equal(A.span(26 * 3600000), '1 d 2 h');
  assert.equal(A.bytes(221184), '216 KB');
  assert.equal(A.validLog('2026-10-31_1345'), true);
  assert.equal(A.validLog('../secrets'), false);
  const log = [{ p: 'twitch', name: 'Ann', text: 'what keyboard is that?', question: true }, { p: 'youtube', name: 'Bo', text: 'Keyboard looks great' },
               { p: 'twitch', name: 'Keyla', text: 'hi' }];
  assert.equal(A.logFilter(log, { text: 'KEYBOARD' }).length, 2);
  assert.equal(A.logFilter(log, { text: 'key', p: 'twitch' }).length, 2);   // names count too
  assert.equal(A.logFilter(log, { questions: true }).length, 1);
  assert.equal(A.logFilter(log, { text: 'keyboard great' }).length, 1);       // every word
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

test('TikTok, Facebook and Rumble reply through the CrossChat window, like YouTube and X', () => {
  assert.equal(A.LIMIT.tiktok, 150); assert.equal(A.LIMIT.facebook, 8000); assert.equal(A.LIMIT.rumble, 200);
  assert.equal(A.name('tiktok'), 'TikTok'); assert.equal(A.NAMES.rumble[1], 'RM');
  const states = { tiktok: 'on', facebook: 'on', rumble: 'off' };
  const m = { p: 'tiktok', kind: 'chat', name: 'luna.makes', text: 'hi' };
  assert.equal(A.canReply(m, { executor: true, states }).ok, true);
  assert.equal(A.canReply(m, { executor: false, states }).ok, false);                   // needs the window with the extension
  assert.match(A.canReply(m, { executor: false, remote: true, states }).why, /streaming PC/);
  assert.equal(A.canReply({ ...m, p: 'rumble' }, { executor: true, states }).ok, false);  // that chat isn't open
  assert.deepEqual(A.targetsFor(states, null, 'off'), ['tiktok', 'facebook']);
  assert.deepEqual(A.tooLong('x'.repeat(151), ['tiktok', 'facebook']), ['tiktok']);
  const mod = A.modMenu(m, { executor: true, states });
  assert.equal(mod.every((e) => !e.ok), true); assert.match(mod[0].why, /Moderate TikTok chat in TikTok/);
});

test('Instagram comments are answered through the CrossChat window, like Facebook', () => {
  assert.equal(A.LIMIT.instagram, 2200); assert.equal(A.name('instagram'), 'Instagram'); assert.equal(A.NAMES.instagram[1], 'IG');
  assert.ok(A.PAGE_PLATFORMS.includes('instagram')); assert.ok(A.TTS_PLATFORMS.includes('instagram'));
  const states = { instagram: 'on', facebook: 'off' };
  const m = { p: 'instagram', kind: 'chat', name: 'lena.park', text: 'hi' };
  assert.equal(A.canReply(m, { executor: true, states }).ok, true);
  assert.equal(A.canReply(m, { executor: false, states }).ok, false);
  assert.deepEqual(A.targetsFor(states, null, 'off'), ['instagram']);
  assert.deepEqual(A.tooLong('x'.repeat(2201), ['instagram']), ['instagram']);
  assert.match(A.modMenu(m, { executor: true, states })[0].why, /Moderate Instagram chat in Instagram/);
});

test('a platform CrossChat does not know never breaks anything', () => {
  const m = { p: 'myspace', kind: 'chat', name: 'tom', text: 'hello' };
  assert.equal(A.name('myspace'), 'myspace');
  assert.equal(A.canReply(m, { executor: true, states: { myspace: 'on' } }).ok, false);
  assert.equal(A.modMenu(m, { executor: true }).every((e) => !e.ok), true);
  assert.deepEqual(A.targetsFor({ myspace: 'on', twitch: 'off' }, null, 'off'), []);
  assert.deepEqual(A.logFilter([m, { p: 'tiktok', name: 'a', text: 'b' }], { p: 'tiktok' }).length, 1);
});

test('the update notice only ever links to a CrossChat release page on GitHub', () => {
  const page = 'https://github.com/RandyNorthrup/crosschat-obs/releases/tag/v1.7.0';
  assert.equal(A.releaseLink(page), page);
  for (const bad of ['https://evil.example/', 'http://github.com/RandyNorthrup/crosschat-obs/releases/tag/v1.7.0', page + '?x=1', page + '/../../evil',
    'https://github.com/someone/else/releases/tag/v1.7.0', 'javascript:alert(1)', page + '\n', '', null, undefined, {}, ['x']]) assert.equal(A.releaseLink(bad), '', String(bad));
});

test('an extension older than CrossChat is noticed, anything else is not', () => {
  assert.equal(A.extensionBehind('1.6.0', '1.7.0'), true);
  assert.equal(A.extensionBehind('1.7.0', '1.7.1'), true);
  assert.equal(A.extensionBehind('1.9.9', '1.10.0'), true);
  for (const [ext, hub] of [['1.7.0', '1.7.0'], ['1.8.0', '1.7.0'], ['1.10.0', '1.9.9'], ['', '1.7.0'], [undefined, '1.7.0'], ['1.6.0', ''],
    ['1.6', '1.7.0'], ['1.6.0<b>', '1.7.0'], [{}, '1.7.0']]) assert.equal(A.extensionBehind(ext, hub), false, String(ext) + ' vs ' + String(hub));
});

test('a Discord webhook URL is recognised before it goes to the hub', () => {
  const token = 'abcDEF123_-'.repeat(6);
  assert.equal(A.discordWebhook('https://discord.com/api/webhooks/123456789012345678/' + token), true);
  assert.equal(A.discordWebhook(' https://canary.discord.com/api/webhooks/123456789012345678/' + token + ' '), true);
  for (const bad of ['http://discord.com/api/webhooks/123456789012345678/' + token, 'https://discord.com.evil.example/api/webhooks/123456789012345678/' + token,
    'https://discord.com/api/webhooks/123456789012345678/' + token + '?x', 'https://discord.com/api/webhooks/abc/' + token, '']) {
    assert.equal(A.discordWebhook(bad), false, bad);
  }
});
