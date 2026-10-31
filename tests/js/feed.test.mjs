// Tests for hub/web/feed.js: third-party emotes and the chat widget's delay. Run: node --test "tests/js/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const F = require('../../hub/web/feed.js');
const T = require('../../hub/web/theme.js');

const MAP = F.emoteMap({ KEKW: 'https://cdn.7tv.app/emote/1/2x.webp', catJAM: 'https://cdn.betterttv.net/emote/2/2x', Kappa: 'https://cdn.frankerfacez.com/3' });

test('the emote list keeps one-word codes with https pictures', () => {
  const m = F.emoteMap({ ok: 'https://a/b.png', 'two words': 'https://a/c.png', plain: 'http://a/d.png', js: 'javascript:alert(1)', quote: 'https://a/"x', '': 'https://a/e' });
  assert.deepEqual([...m.keys()], ['ok']);
  assert.equal(F.emoteMap(null).size, 0);
  assert.equal(F.emoteMap(['https://a/b.png']).size, 0);
  assert.equal(F.emoteMap(JSON.parse('{"__proto__": "https://a/p.png"}')).get('__proto__'), 'https://a/p.png');   // a plain word to a Map
});

test('third-party emotes replace whole words only, matching case', () => {
  const out = F.withEmotes([{ text: 'lol KEKW, KEKW kekw xKEKW catJAM' }], MAP);
  assert.deepEqual(out, [{ text: 'lol KEKW, ' }, { url: 'https://cdn.7tv.app/emote/1/2x.webp', alt: 'KEKW' }, { text: ' kekw xKEKW ' },
                         { url: 'https://cdn.betterttv.net/emote/2/2x', alt: 'catJAM' }]);
  assert.deepEqual(F.withEmotes([{ text: 'KEKW' }], MAP), [{ url: 'https://cdn.7tv.app/emote/1/2x.webp', alt: 'KEKW' }]);
  assert.deepEqual(F.withEmotes([{ text: 'plain words' }], new Map()), [{ text: 'plain words' }]);
  assert.deepEqual(F.withEmotes([{ text: 'a KEKW\tb' }], MAP).map((p) => p.alt || p.text), ['a ', 'KEKW', '\tb']);
});

test("Twitch's own emotes win over a third-party code with the same name", () => {
  const pieces = T.emotePieces('Kappa hi Kappa', '25:0-4');                   // only the first Kappa is Twitch's
  assert.deepEqual(F.withEmotes(pieces, MAP), [{ emote: '25', alt: 'Kappa' }, { text: ' hi ' }, { url: 'https://cdn.frankerfacez.com/3', alt: 'Kappa' }]);
});

test('delete, purge and hide events take the right messages', () => {
  const m = { id: 'tw-1', p: 'twitch', name: 'Ann', handle: 'ann_k' };
  assert.equal(F.takes({ type: 'delete', id: 'tw-1' }, m), true);
  assert.equal(F.takes({ type: 'delete', id: 'tw-2' }, m), false);
  assert.equal(F.takes({ type: 'purge', p: 'twitch', name: 'ann' }, m), true);
  assert.equal(F.takes({ type: 'purge', p: 'youtube', name: 'ann' }, m), false);
  assert.equal(F.takes({ type: 'hide', name: 'ANN_K' }, m), true);              // any platform, name or handle
  assert.equal(F.takes({ type: 'hide', name: '' }, m), false);
  assert.equal(F.takes({ type: 'clear' }, m), false);
});

test('the delay holds messages and drops one deleted or hidden meanwhile', () => {
  const q = F.holdQueue();
  const a = { id: 'a', p: 'twitch', name: 'ann' }, b = { id: 'b', p: 'kick', name: 'bo' }, c = { id: 'c', p: 'twitch', name: 'ann' };
  q.add(a, 1000); q.add(b, 1500); q.add(c, 2000);
  assert.equal(q.next(), 1000);
  assert.deepEqual(q.due(999), []);
  assert.equal(q.drop((m) => F.takes({ type: 'delete', id: 'b' }, m)), 1);     // deleted while held: never shows
  assert.deepEqual(q.due(1000), [a]);
  assert.equal(q.drop((m) => F.takes({ type: 'purge', p: 'twitch', name: 'ann' }, m)), 1);
  assert.equal(q.size, 0);
  assert.equal(q.next(), Infinity);
  q.add(a, 5); q.add(b, 3);
  assert.deepEqual(q.due(10), [a, b]);                                          // in arrival order
  q.add(a, 5); q.clear();
  assert.deepEqual(q.due(10), []);
});

test('themes carry the delay and the first-chatter highlight', () => {
  const t = T.merge({ chat: { delay: 90 }, message: { firstHighlight: false } });
  assert.equal(t.chat.delay, 60);
  assert.equal(t.message.firstHighlight, false);
  assert.equal(T.merge({}).chat.delay, 0);
  assert.equal(T.merge({}).message.firstHighlight, true);
  assert.deepEqual(T.problems({ chat: { delay: 5 } }), []);
});
