// Tests for extension/background.js: where YouTube moderation is carried out. YouTube offers the channel owner
// Remove, timeout and Hide user only on its own chat page, not in the chat embedded in the CrossChat window.
// Run: node --test "tests/js/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { extensionSource } from './extension-files.mjs';

// background.js as a service worker runs it, importScripts included (windows.js is tested by itself). Each call is a fresh worker.
function worker() {
  const importScripts = () => {};
  return new Function('importScripts', extensionSource('background.js') + '\nreturn { moderate, chatPageFor, youtubeChatPage, stillNeeded, post };')(importScripts);
}

const VIDEO = 'Ilc1JaZfDxA';
const EMBEDDED = 'https://www.youtube.com/live_chat?v=' + VIDEO + '&embed_domain=127.0.0.1';
const POPOUT = 'https://www.youtube.com/live_chat?is_popout=1&v=' + VIDEO;

// A stand-in for the browser: the tabs open now, and what the extension sent where.
// dead: tabs whose page script doesn't answer (loaded before the extension was reloaded) until they are reloaded.
function browser(tabs, { windows = [{ id: 7, focused: true }], ready = true, targets = { youtube_video: VIDEO, live: true }, dead = [] } = {}) {
  let listener;
  const sent = [];
  const created = [];
  const removed = [];
  const reloaded = [];
  const silent = new Set(dead);
  globalThis.fetch = async () => {
    if (!targets) throw new TypeError('Failed to fetch');
    return { json: async () => targets };
  };
  globalThis.chrome = {
    runtime: { onMessage: { addListener(fn) { listener = fn; } } },
    tabs: {
      query: async () => tabs,
      remove: async (ids) => { removed.push(...[].concat(ids)); },
      reload: async (id) => { reloaded.push(id); silent.delete(id); },
      create: async (o) => { const t = { id: 100 + created.length, url: o.url, windowId: o.windowId, active: o.active }; created.push(t); return t; },
      sendMessage: async (id, message) => {
        sent.push({ id, message });
        if (silent.has(id)) throw new Error('Could not establish connection. Receiving end does not exist.');
        if (message.type === 'yt-ready') return { ok: ready };
        return { ok: true, by: id };
      },
    },
    windows: {
      getAll: async () => windows,
      create: async (o) => { const t = { id: 200, url: o.url }; created.push({ ...t, window: o }); return { tabs: [t] }; },
    },
  };
  const BG = worker();
  return { BG, sent, created, removed, reloaded, says: (message, sender) => listener(message, sender, () => {}) };
}
const OURS = POPOUT + '&crosschat=1';

test("YouTube's own chat page for the live is told apart from the embedded copy and other lives", () => {
  const { BG } = browser([]);
  assert.equal(BG.chatPageFor(POPOUT, VIDEO), true);
  assert.equal(BG.chatPageFor('https://www.youtube.com/live_chat?v=' + VIDEO, VIDEO), true);
  assert.equal(BG.chatPageFor(EMBEDDED, VIDEO), false);
  assert.equal(BG.chatPageFor('https://www.youtube.com/live_chat?is_popout=1&v=other123456', VIDEO), false);
  assert.equal(BG.chatPageFor('https://www.youtube.com/watch?v=' + VIDEO, VIDEO), false);
  assert.equal(BG.chatPageFor('not a url', VIDEO), false);
});

test('moderation goes to an open chat pop-out, never to the embedded copy', async () => {
  const { BG, sent, created } = browser([{ id: 1, url: EMBEDDED }, { id: 2, url: POPOUT }]);
  const answer = await BG.moderate({ p: 'youtube', action: 'timeout', message_id: 'abc', seconds: 300 }, { id: 9 });
  assert.deepEqual(answer, { ok: true, by: 2 });
  assert.deepEqual(sent.map((s) => s.id), [2, 2]);
  assert.equal(sent[0].message.type, 'yt-ready');
  assert.deepEqual(sent[1].message, { type: 'yt-mod', video: VIDEO, action: 'timeout', message_id: 'abc', seconds: 300 });
  assert.equal(created.length, 0);
});

test('an open pop-out whose page script is gone (the extension was reloaded) is reloaded, then used', async () => {
  const { BG, created, reloaded } = browser([{ id: 3, url: POPOUT + '&crosschat=1' }], { dead: [3] });
  const tabs = await BG.youtubeChatPage(VIDEO, 1);
  assert.deepEqual(reloaded, [3]);
  assert.deepEqual(tabs.map((t) => t.id), [3]);
  assert.equal(created.length, 0);
});

test('with no chat pop-out open, one is opened in a background tab and used once it is ready', async () => {
  const { BG, sent, created } = browser([{ id: 1, url: EMBEDDED }]);
  const tabs = await BG.youtubeChatPage(VIDEO, 1);
  assert.equal(created.length, 1);
  assert.equal(created[0].url, OURS);
  assert.equal(created[0].active, false);
  assert.equal(created[0].windowId, 7);
  assert.deepEqual(tabs.map((t) => t.id), [100]);
  assert.deepEqual(sent.map((s) => s.message.type), ['yt-ready']);
});

test('with no browser window open, the chat pop-out gets a minimized window of its own, not the focus', async () => {
  const { BG, created } = browser([], { windows: [] });
  await BG.youtubeChatPage(VIDEO, 1);
  assert.equal(created.length, 1);
  assert.equal(created[0].window.focused, false);
  assert.equal(created[0].window.state, 'minimized');
});

test('the pop-out is opened once: two moderations at the same time share it, and later ones reuse it', async () => {
  const tabs = [];
  const { BG, created } = browser(tabs);
  const [a, b] = await Promise.all([BG.youtubeChatPage(VIDEO, 5), BG.youtubeChatPage(VIDEO, 5)]);
  assert.equal(created.length, 1);
  assert.deepEqual(a, b);
  tabs.push({ id: created[0].id, url: created[0].url });          // the tab is there now
  assert.deepEqual((await BG.youtubeChatPage(VIDEO, 5)).map((t) => t.id), [created[0].id]);
  assert.equal(created.length, 1);
});

test('a tab still loading counts as open (its address is not committed yet)', async () => {
  const { BG, created } = browser([{ id: 4, url: '', pendingUrl: OURS }]);
  assert.deepEqual((await BG.youtubeChatPage(VIDEO, 1)).map((t) => t.id), [4]);
  assert.equal(created.length, 0);
});

test("CrossChat's pop-out for an earlier live is closed; one the streamer opened is left alone", async () => {
  const earlier = 'https://www.youtube.com/live_chat?is_popout=1&v=earlier1234&crosschat=1';
  const theirs = 'https://www.youtube.com/live_chat?is_popout=1&v=earlier1234';
  const { BG, removed } = browser([{ id: 5, url: earlier }, { id: 6, url: theirs }]);
  await BG.youtubeChatPage(VIDEO, 1);
  assert.deepEqual(removed, [5]);
});

test('the pop-out closes itself once the live is over, another live started, or CrossChat is gone twice running', async () => {
  const tab = { id: 9 };
  let t = browser([], { targets: { youtube_video: VIDEO, live: true } });
  assert.deepEqual(await t.BG.stillNeeded({ video: VIDEO, misses: 0 }, { tab, url: OURS }), { keep: true, reached: true });
  assert.deepEqual(t.removed, []);
  t = browser([], { targets: { youtube_video: VIDEO, live: false } });
  assert.equal((await t.BG.stillNeeded({ video: VIDEO, misses: 0 }, { tab, url: OURS })).keep, false);
  assert.deepEqual(t.removed, [9]);
  t = browser([], { targets: { youtube_video: 'another1234', live: true } });
  assert.equal((await t.BG.stillNeeded({ video: VIDEO, misses: 0 }, { tab, url: OURS })).keep, false);
  t = browser([], { targets: null });
  assert.deepEqual(await t.BG.stillNeeded({ video: VIDEO, misses: 0 }, { tab, url: OURS }), { keep: true, reached: false });
  assert.deepEqual(t.removed, []);
  assert.equal((await t.BG.stillNeeded({ video: VIDEO, misses: 1 }, { tab, url: OURS })).keep, false);
  assert.deepEqual(t.removed, [9]);
});

test("a pop-out the streamer opened by hand is never closed", async () => {
  const t = browser([], { targets: { youtube_video: VIDEO, live: false } });
  assert.equal((await t.BG.stillNeeded({ video: VIDEO, misses: 5 }, { tab: { id: 3 }, url: POPOUT })).keep, true);
  assert.deepEqual(t.removed, []);
});

test('a chat page that never gets ready is asked anyway, after a bounded wait', async () => {
  const { BG, sent } = browser([], { ready: false });
  const tabs = await BG.youtubeChatPage(VIDEO, 1);
  assert.equal(tabs.length, 1);
  assert.equal(sent.filter((s) => s.message.type === 'yt-ready').length, 1);     // once: then it is the page that says
});

const tick = () => new Promise((r) => setTimeout(r, 0));

test("a chat page that says its chat has come goes ahead at once, no polling and no wait to the end", async () => {
  const { BG, created, sent, says } = browser([], { ready: false });
  let done = false;
  const opened = BG.youtubeChatPage(VIDEO, 2000).then((tabs) => { done = true; return tabs; });
  await tick();
  assert.equal(created.length, 1);
  assert.equal(done, false);
  says({ type: 'yt-chat-ready', data: { video: VIDEO } }, { url: OURS, tab: { id: 100 } });
  await tick();
  assert.equal(done, true, 'not waiting out the time');
  assert.deepEqual((await opened).map((t) => t.id), [100]);
  assert.equal(sent.filter((s) => s.message.type === 'yt-ready').length, 1);
});

test("word from another tab or another live doesn't end the wait", async () => {
  const { BG, says } = browser([], { ready: false });
  let done = false;
  const opened = BG.youtubeChatPage(VIDEO, 30).then((tabs) => { done = true; return tabs; });
  await tick();
  says({ type: 'yt-chat-ready', data: { video: VIDEO } }, { url: OURS, tab: { id: 999 } });
  says({ type: 'yt-chat-ready', data: { video: 'another1234' } }, { url: OURS, tab: { id: 100 } });
  await tick();
  assert.equal(done, false);
  await opened;
  assert.equal(done, true);
});

test('only a YouTube chat page can say so', async () => {
  const { BG, says } = browser([], { ready: false });
  let done = false;
  BG.youtubeChatPage(VIDEO, 30).then(() => { done = true; });
  await tick();
  says({ type: 'yt-chat-ready', data: { video: VIDEO } }, { url: 'https://www.tiktok.com/@x/live', tab: { id: 100 } });
  await tick();
  assert.equal(done, false);
});

test('reply limits count characters as the hub does, so emoji are not counted twice', async () => {
  const { BG, sent } = browser([{ id: 4, url: 'https://studio.x.com/live/abc' }]);
  const fits = await BG.post({ to: ['x'], text: '😀'.repeat(140) }, null);
  assert.deepEqual(fits, { x: { ok: true, by: 4 } });
  assert.equal(sent.at(-1).message.type, 'x-say');
  const long = await BG.post({ to: ['x'], text: '😀'.repeat(141) }, null);
  assert.deepEqual(long, { x: { ok: false, why: 'X takes 140 characters at most' } });
});

test('Twitch and Kick never go through the extension', async () => {
  const { BG, sent } = browser([]);
  assert.deepEqual(await BG.post({ to: ['twitch', 'kick'], text: 'hi' }, null),
    { twitch: { ok: false, why: 'not through the extension' }, kick: { ok: false, why: 'not through the extension' } });
  assert.equal(sent.length, 0);
});
