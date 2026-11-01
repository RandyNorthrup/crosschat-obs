// Alerts look the same for every platform: hub/web/theme.js alertKind, alertParts and alertLine, used by the alerts
// widget, the chat feed on stream and the CrossChat window. Run: node --test "tests/js/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const T = require('../../hub/web/theme.js');
const I = require('../../hub/web/icons.js');
const A = require('../../hub/web/app.js');

const theme = T.merge({});
const title = (m, t) => T.alertParts(m, t || theme, I.NAMES[m.p]).parts.map((p) => (p.text !== undefined ? p.text : p.value)).join('');
const ev = (p, alert, name, amount, system, text) => ({ type: 'msg', kind: 'event', p, alert, name, amount: amount || '', system: system || '', text: text || '' });

// Each platform's events exactly as the hub sends them (hub.py: twitch_notice, yt_poll, kick_alert, rumble_read).
const EVENTS = [
  [ev('twitch', 'sub', 'kiwi_codes', '', 'kiwi_codes subscribed at Tier 1.'), 'sub', 'kiwi_codes just subscribed!'],
  [ev('twitch', 'resub', 'nightowl_42', '6', 'nightowl_42 subscribed for 6 months!', 'half a year'), 'resub', 'nightowl_42 resubscribed for 6 months!'],
  [ev('twitch', 'gift', 'AriaPlays', 'a sub', 'AriaPlays gifted a Tier 1 sub to kiwi_codes!'), 'gift', 'AriaPlays gifted a sub!'],
  [ev('twitch', 'gift', 'AriaPlays', '5 subs', 'AriaPlays is gifting 5 Tier 1 Subs!'), 'gift', 'AriaPlays gifted 5 subs!'],
  [ev('twitch', 'raid', 'raid_leader', '37', '37 raiders from raid_leader have joined!'), 'raid', 'raid_leader is raiding with 37 viewers!'],
  [ev('twitch', 'cheer', 'bitbucket', '500 bits', 'bitbucket cheered 500 bits', 'Cheer500 great stream'), 'cheer', 'bitbucket cheered 500 bits!'],
  [ev('youtube', 'superchat', 'Sam Ortiz', '$5.00', 'Super Chat $5.00', 'Keep it up!'), 'superchat', 'Sam Ortiz sent a Super Chat: $5.00'],
  [ev('youtube', 'superchat', 'Priya N', '$2.00', 'Super Sticker $2.00'), 'sticker', 'Priya N sent a Super Sticker: $2.00'],
  [ev('youtube', 'member', 'Rafael Gomes', '', 'Welcome to Members!'), 'member', 'Rafael Gomes became a member!'],
  [ev('youtube', 'gift', 'Maya Chen', '5 memberships', 'Maya Chen gifted 5 memberships'), 'gift', 'Maya Chen gifted 5 memberships!'],
  [ev('kick', 'sub', 'turbo_kat', '', 'turbo_kat subscribed'), 'sub', 'turbo_kat just subscribed!'],
  [ev('kick', 'resub', 'turbo_kat', '3', 'turbo_kat subscribed for 3 months'), 'resub', 'turbo_kat resubscribed for 3 months!'],
  [ev('kick', 'gift', 'glitchfox', '5 subs', 'glitchfox gifted 5 subs'), 'gift', 'glitchfox gifted 5 subs!'],
  [ev('kick', 'raid', 'glitchfox', '12', 'glitchfox is raiding with 12 viewers'), 'raid', 'glitchfox is raiding with 12 viewers!'],
  [ev('rumble', 'superchat', 'trailhead_tv', '$5.00', 'trailhead_tv sent a $5.00 Rant', 'Keep the builds coming'), 'rant', 'trailhead_tv sent a Rant: $5.00'],
  [ev('rumble', 'sub', 'maple_moto', '', 'maple_moto subscribed'), 'sub', 'maple_moto just subscribed!'],
  [ev('rumble', 'gift', 'maple_moto', '2 subs', 'maple_moto gifted 2 subs'), 'gift', 'maple_moto gifted 2 subs!'],
];

test('every platform\'s alerts get the same kind of sentence, with the name and the amount picked out', () => {
  EVENTS.forEach(([m, kind, sentence]) => {
    const a = T.alertParts(m, theme, I.NAMES[m.p]);
    assert.equal(a.kind, kind, m.p + ' ' + m.alert);
    assert.equal(title(m), sentence);
    assert.deepEqual(a.parts[0], { key: 'name', value: m.name }, sentence);
    if (m.amount) assert.ok(a.parts.some((p) => p.key === 'amount' && p.value === m.amount), sentence);
    assert.equal(a.words, !!m.text, sentence);                    // what the viewer wrote goes with it
    assert.ok(I.PATHS[m.p], 'an icon for ' + m.p);
  });
});

test('Rants and Super Stickers have their own switches and sentences', () => {
  assert.ok(T.ALERTS.includes('rant') && T.ALERTS.includes('sticker'));
  T.ALERTS.forEach((kind) => {
    assert.equal(typeof T.DEFAULTS.alerts.labels[kind], 'string', kind);
    assert.equal(T.DEFAULTS.alerts.types[kind], !['like', 'join'].includes(kind), kind);   // TikTok likes and joins start off
  });
  const quiet = T.merge({ alerts: { types: { rant: false }, labels: { rant: '{name} ranted {amount} on {platform}' } } });
  assert.equal(quiet.alerts.types.rant, false);
  assert.equal(quiet.alerts.types.superchat, true);              // Super Chats still show
  assert.equal(title(EVENTS[14][0], quiet), 'trailhead_tv ranted $5.00 on Rumble');
  assert.equal(title(EVENTS[6][0], quiet), 'Sam Ortiz sent a Super Chat: $5.00');
});

test('a missing amount never leaves a gap in the sentence', () => {
  assert.equal(title(ev('twitch', 'resub', 'kiwi_codes', '', 'kiwi_codes subscribed at Tier 1.')), 'kiwi_codes resubscribed!');
  assert.equal(title(ev('twitch', 'raid', 'raid_leader', '')), 'raid_leader is raiding!');
  assert.equal(title(ev('rumble', 'superchat', 'trailhead_tv', '')), 'trailhead_tv sent a Rant!');
  assert.equal(title(ev('twitch', 'cheer', 'bitbucket', '  ')), 'bitbucket cheered!');
  // the streamer's own sentence is kept, just without a double space
  const own = T.merge({ alerts: { labels: { resub: '{name} is back for {amount} months, welcome!' } } });
  assert.equal(title(ev('twitch', 'resub', 'kiwi_codes', ''), own), 'kiwi_codes is back for months, welcome!');
  assert.equal(title(ev('kick', 'sub', '', '')), 'Someone just subscribed!');
});

test('unknown alert kinds degrade to the platform\'s own words', () => {
  const boost = ev('tiktok', 'boost', 'sunny.daze', '', 'sunny.daze boosted the LIVE', 'woo');
  assert.equal(T.alertKind(boost), 'other');
  assert.equal(title(boost), 'sunny.daze boosted the LIVE');
  assert.equal(T.alertParts(boost, theme).words, true);
  assert.equal(T.alertLine(boost, theme), 'sunny.daze boosted the LIVE · woo');
  // Twitch's "other" notices carry its sentence and the viewer's words in text already
  const notice = ev('twitch', 'other', 'AriaPlays', '', 'AriaPlays shared an announcement', 'AriaPlays shared an announcement  Giveaway soon!');
  assert.equal(T.alertLine(notice, theme), 'AriaPlays shared an announcement Giveaway soon!');
  assert.equal(T.alertLine(ev('x', undefined, 'Lena', '', '', 'hello'), theme), 'hello');
  assert.equal(T.alertLine(ev('youtube', 'other', 'Lena', '', '', ''), theme), 'Lena');
  assert.equal(T.alertLine({}, theme), 'Someone');
  assert.equal(T.alertKind(null), 'other');
  const blank = T.merge({ alerts: { labels: { sub: '   ' } } });            // a label emptied in the Studio
  assert.equal(title(ev('kick', 'sub', 'turbo_kat', '', 'turbo_kat subscribed'), blank), 'turbo_kat subscribed');
});

test('the chat feed and the chat window use the same one-line sentence', () => {
  assert.equal(T.alertLine(EVENTS[6][0], theme, 'YouTube'), 'Sam Ortiz sent a Super Chat: $5.00 · Keep it up!');
  assert.equal(T.alertLine(EVENTS[14][0], theme, 'Rumble'), 'trailhead_tv sent a Rant: $5.00 · Keep the builds coming');
  assert.equal(T.alertLine(EVENTS[2][0], theme, 'Twitch'), 'AriaPlays gifted a sub!');
  const withText = T.merge({ alerts: { labels: { cheer: '{name}: {text} ({amount})' } } });
  assert.equal(T.alertLine(EVENTS[5][0], withText), 'bitbucket: Cheer500 great stream (500 bits)');   // {text} used: not twice
});

test('viewer text in an alert stays text', () => {
  const m = ev('youtube', 'superchat', '<img src=x onerror=alert(1)>', '$1.00', 'Super Chat $1.00', '<b>hi</b>');
  const a = T.alertParts(m, theme);
  assert.deepEqual(a.parts[0], { key: 'name', value: '<img src=x onerror=alert(1)>' });   // pages put pieces in with textContent
});

test('the chat window and the Theme Studio name every alert kind', () => {
  T.ALERTS.filter((kind) => kind !== 'other').forEach((kind) => assert.notEqual(A.alertWord(kind), 'Event', kind));
  assert.equal(A.alertWord('rant'), 'Rant');
  assert.equal(A.alertWord('whatever'), 'Event');
  const studio = readFileSync(path.join(here, '..', '..', 'hub', 'web', 'studio.js'), 'utf8');
  const names = /const ALERT_NAMES = \{([\s\S]*?)\};/.exec(studio)[1];
  T.ALERTS.forEach((kind) => assert.match(names, new RegExp('\\b' + kind + ': \''), kind));
});
