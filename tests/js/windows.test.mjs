// Tests for extension/windows.js: which windows the extension may place, move and close for the hub, and how.
// A stand-in for chrome.windows behaves as the real one showed on macOS and Linux (scripts/window_e2e.py runs the
// real one): windows opened with --app are type "app"; a tab's address is there only on the extension's own sites.
// Run: node --test "tests/js/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadExtension } from './extension-files.mjs';

const W = loadExtension('windows.js').CrossChatWindows;

const CHAT = 'http://127.0.0.1:4466/';
const TIKTOK = 'https://www.tiktok.com/@someone/live';

// chrome.windows with these windows: { id, type, state, tabs: [{ id, url, pendingUrl }] }. Records what was done.
function browser(list) {
  const wins = list.map((w) => ({ state: 'normal', left: 0, top: 0, width: 800, height: 600, ...w }));
  const did = [];
  const copy = (w) => JSON.parse(JSON.stringify(w));
  const visible = (w, types) => (types || ['normal', 'popup']).includes(w.type);
  return {
    did,
    wins,
    async getAll(q = {}) { return wins.filter((w) => visible(w, q.windowTypes)).map((w) => (q.populate ? copy(w) : { ...copy(w), tabs: undefined })); },
    async get(id, q = {}) {
      const w = wins.find((x) => x.id === id && visible(x, q.windowTypes));
      if (!w) throw new Error('No window with id: ' + id + '.');
      return copy(w);
    },
    async update(id, change) {
      const w = wins.find((x) => x.id === id);
      if (!w) throw new Error('No window with id: ' + id + '.');
      if (change.state && change.state !== 'normal' && ('left' in change || 'width' in change)) throw new Error('Invalid value for state');
      did.push(['update', id, change]);
      Object.assign(w, change);
      return copy(w);
    },
    async remove(id) {
      const at = wins.findIndex((x) => x.id === id);
      if (at < 0) throw new Error('No window with id: ' + id + '.');
      did.push(['remove', id]);
      wins.splice(at, 1);
    },
  };
}
const tab = (id, url, extra) => ({ id, url, ...extra });
const now = () => Promise.resolve();       // (no real waiting in the tests)
const BOX = [10, 20, 400, 600];
const PLACED = { left: 10, top: 20, width: 400, height: 600 };

// The chat window CrossChat opened (window 5), a tab of the chat in someone's ordinary window (window 2, beside
// another tab), an ordinary window with a single chat tab (window 3), and an app window of another site (window 4).
const everyday = () => browser([
  { id: 2, type: 'normal', tabs: [tab(20, CHAT), tab(21, 'https://example.com/')] },
  { id: 3, type: 'normal', tabs: [tab(30, CHAT)] },
  { id: 4, type: 'app', tabs: [tab(40, undefined)] },        // (its address isn't the extension's to read)
  { id: 5, type: 'app', tabs: [tab(50, CHAT)] },
]);

test('the chat window CrossChat opened moves itself', async () => {
  const b = everyday();
  assert.deepEqual(await W.job({ action: 'place', role: 'chat', box: BOX }, { id: 50, windowId: 5 }, b, now), { ok: true, window: 5 });
  assert.deepEqual(b.did, [['update', 5, PLACED]]);
});

test('asked from a chat in a tab of an ordinary window, the CrossChat chat window moves, never that window', async () => {
  for (const [id, windowId] of [[20, 2], [30, 3]]) {
    const b = everyday();
    assert.deepEqual(await W.job({ action: 'place', role: 'chat', box: BOX }, { id, windowId }, b, now), { ok: true, window: 5 });
    assert.deepEqual(b.did, [['update', 5, PLACED]]);
  }
});

test('with no CrossChat chat window in the browser, nothing moves and the hub hears there is none', async () => {
  const b = browser([{ id: 2, type: 'normal', tabs: [tab(20, CHAT)] }, { id: 3, type: 'normal', tabs: [tab(30, CHAT)] }]);
  assert.deepEqual(await W.job({ action: 'place', role: 'chat', box: BOX }, { id: 20, windowId: 2 }, b, now),
    { ok: false, why: 'no chat window is open', none: true });
  assert.deepEqual(b.did, []);
});

test('the page cannot name another window for the chat window', async () => {
  const b = everyday();
  const answer = await W.job({ action: 'place', role: 'chat', box: BOX, window: 4 }, { id: 30, windowId: 3 }, b, now);
  assert.deepEqual(answer, { ok: true, window: 5 });
  assert.deepEqual(b.did, [['update', 5, PLACED]]);
});

test('of several chat windows, the asking one moves, else the newest', async () => {
  const b = browser([{ id: 5, type: 'app', tabs: [tab(50, CHAT)] }, { id: 6, type: 'app', tabs: [tab(60, CHAT)] }]);
  assert.equal((await W.job({ action: 'place', role: 'chat', box: BOX }, { id: 50, windowId: 5 }, b, now)).window, 5);
  assert.equal((await W.job({ action: 'place', role: 'chat', box: BOX }, null, b, now)).window, 6);
});

test('a minimized or maximized chat window is made normal first, then placed', async () => {
  const b = browser([{ id: 5, type: 'app', state: 'maximized', tabs: [tab(50, CHAT)] }]);
  assert.equal((await W.job({ action: 'place', role: 'chat', box: BOX }, { id: 50, windowId: 5 }, b, now)).ok, true);
  assert.deepEqual(b.did, [['update', 5, { state: 'normal' }], ['update', 5, PLACED]]);
});

test('a window the desktop sizes again just after it opened is placed again, a few times at most', async () => {
  // as KWin did on Wayland: the first size given to a window that had just opened didn't take
  const b = everyday();
  const update = b.update;
  let refused = 1;
  b.update = async (id, change) => {
    if (refused-- > 0) { b.did.push(['update (undone by the desktop)', id, change]); return {}; }
    return update(id, change);
  };
  assert.equal((await W.job({ action: 'place', role: 'chat', box: BOX }, { id: 50, windowId: 5 }, b, now)).ok, true);
  assert.deepEqual(b.did, [['update (undone by the desktop)', 5, PLACED], ['update', 5, PLACED]]);
  // as KWin did through XWayland: a window kept maximized one way takes no height until it is maximized and restored
  const stubborn = everyday();
  stubborn.update = async (id, change) => { stubborn.did.push(['update', id, change]); return {}; };
  assert.equal((await W.job({ action: 'place', role: 'chat', box: BOX }, { id: 50, windowId: 5 }, stubborn, now)).ok, true);
  assert.deepEqual(stubborn.did.map(([, , change]) => change.state || 'bounds'),
    ['bounds', 'bounds', 'maximized', 'normal', 'bounds']);       // W.PLACE_TRIES placings, then it stops trying
  assert.equal(W.PLACE_TRIES, 3);
});

test('two placings of one window at once happen one after the other, and the later one is where it ends up', async () => {
  // as on a Mac: Open chat pressed while the chat window's first placing was still being checked
  const b = everyday();
  const tick = () => new Promise((r) => setTimeout(r, 1));
  const MOVED = [100, 140, 460, 600];
  const first = W.job({ action: 'place', role: 'chat', box: BOX }, { id: 50, windowId: 5 }, b, tick);
  const second = W.job({ action: 'place', role: 'chat', box: MOVED }, { id: 50, windowId: 5 }, b, tick);
  assert.deepEqual(await Promise.all([first, second]), [{ ok: true, window: 5 }, { ok: true, window: 5 }]);
  assert.deepEqual(b.did, [['update', 5, PLACED], ['update', 5, { left: 100, top: 140, width: 460, height: 600 }]]);
  const now = b.wins.find((w) => w.id === 5);
  assert.deepEqual([now.left, now.top, now.width, now.height], MOVED);
});

test('closing the chat closes every chat window CrossChat opened, and only those, after answering', async () => {
  const b = browser([
    { id: 2, type: 'normal', tabs: [tab(20, CHAT)] },
    { id: 5, type: 'app', tabs: [tab(50, CHAT)] },
    { id: 6, type: 'app', tabs: [tab(60, CHAT + '?dry')] },
    { id: 7, type: 'app', tabs: [tab(70, CHAT + 'studio')] },        // the Theme Studio is not the chat window
    { id: 8, type: 'app', tabs: [tab(80, 'http://127.0.0.1:4477/')] }, // the demo, on its own port
  ]);
  let later, timeUp;
  const answer = await W.job({ action: 'close', role: 'chat' }, { id: 50, windowId: 5 }, b, (ms) => { later = ms; return new Promise((r) => { timeUp = r; }); });
  assert.deepEqual(answer, { ok: true, windows: [5, 6] });
  assert.equal(later, W.CLOSE_LATEST);
  assert.deepEqual(b.did, []);                            // its answer has to reach the hub before that window goes
  assert.deepEqual(await W.job({ action: 'answered', role: 'chat' }, { id: 50, windowId: 5 }, b, now), { ok: true });
  assert.deepEqual(b.did, [['remove', 5], ['remove', 6]]);
  timeUp();                                               // the time running out after that does nothing more
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(b.did, [['remove', 5], ['remove', 6]]);
});

test('the chat window goes the moment its page says the answer has reached the hub, not after a fixed wait', async () => {
  const b = browser([{ id: 5, type: 'app', tabs: [tab(50, CHAT)] }]);
  const never = () => new Promise(() => {});
  await W.job({ action: 'close', role: 'chat' }, { id: 50, windowId: 5 }, b, never);
  assert.deepEqual(b.did, []);
  await W.job({ action: 'answered', role: 'chat' }, { id: 50, windowId: 5 }, b, never);
  assert.deepEqual(b.did, [['remove', 5]]);
});

test('a page that never says so (an older one, or one that lost the hub) is closed after a while anyway', async () => {
  const b = browser([{ id: 5, type: 'app', tabs: [tab(50, CHAT)] }]);
  await W.job({ action: 'close', role: 'chat' }, { id: 50, windowId: 5 }, b, now);
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(b.did, [['remove', 5]]);
  assert.ok(W.CLOSE_LATEST >= 1000 && W.CLOSE_LATEST <= 10000);
});

test('"answered" with nothing being closed closes nothing', async () => {
  const b = everyday();
  assert.deepEqual(await W.job({ action: 'answered', role: 'chat' }, { id: 50, windowId: 5 }, b, now), { ok: true });
  assert.deepEqual(b.did, []);
});

test('a platform page the hub just opened is found by its address among the new windows, and placed', async () => {
  const b = browser([
    { id: 2, type: 'normal', tabs: [tab(20, TIKTOK)] },                                  // your own tab at that address
    { id: 3, type: 'app', tabs: [tab(30, TIKTOK)] },                                     // open before (known)
    { id: 4, type: 'app', tabs: [tab(40, 'https://www.tiktok.com/@someone_else/live')] },
    { id: 9, type: 'app', tabs: [tab(90, '', { pendingUrl: TIKTOK })] },                 // the new one, still loading
  ]);
  const answer = await W.job({ action: 'place', role: 'tiktok', url: TIKTOK, box: BOX, known: [2, 3, 4], wait: 30 }, { id: 50, windowId: 5 }, b, now);
  assert.deepEqual(answer, { ok: true, window: 9 });
  assert.deepEqual(b.did, [['update', 9, PLACED]]);
});

test("a platform page is waited for while it opens, and not forever", async () => {
  const b = browser([]);
  let waited = 0;
  const sleep = async () => {
    waited += 1;
    if (waited === 3) b.wins.push({ id: 9, type: 'app', state: 'normal', tabs: [tab(90, 'https://studio.x.com/live')] });   // (#golive gone already)
  };
  const answer = await W.job({ action: 'place', role: 'x', url: 'https://studio.x.com/live#golive', box: BOX, known: [], wait: 30 }, null, b, sleep);
  assert.deepEqual(answer, { ok: true, window: 9 });
  const gone = await W.job({ action: 'place', role: 'x', url: 'https://studio.x.com/live', box: BOX, known: [9], wait: 0 }, null, browser([]), now);
  assert.deepEqual(gone, { ok: false, why: 'the window is not open' });
});

test('an address of another site, or none, never names a window', async () => {
  const b = browser([{ id: 9, type: 'app', tabs: [tab(90, TIKTOK)] }, { id: 10, type: 'app', tabs: [tab(100, 'https://evil.example/')] }]);
  for (const url of ['', 'https://evil.example/', 'https://www.tiktok.com.evil.example/', 'javascript:alert(1)']) {
    const answer = await W.job({ action: 'place', role: 'tiktok', url, box: BOX, wait: 0 }, null, b, now);
    assert.equal(answer.ok, false, url);
  }
  const other = await W.job({ action: 'close', role: 'tiktok', url: 'https://evil.example/' }, null, b, now);
  assert.equal(other.ok, false);
  assert.equal((await W.job({ action: 'close', role: 'myspace', url: TIKTOK }, null, b, now)).ok, false);
  assert.deepEqual(b.did, []);
});

test('a recorded window is closed only while it is still that page in a window of its own', async () => {
  const b = browser([
    { id: 9, type: 'app', tabs: [tab(90, 'https://www.facebook.com/live/producer/123')] },
    { id: 10, type: 'app', tabs: [tab(100, undefined)] },                    // gone elsewhere (or the browser restarted)
    { id: 11, type: 'normal', tabs: [tab(110, 'https://www.facebook.com/live/producer')] },
    { id: 12, type: 'app', tabs: [tab(120, 'https://www.facebook.com/live/producer'), tab(121, 'https://www.facebook.com/')] },
  ]);
  const close = (window) => W.job({ action: 'close', role: 'facebook', url: 'https://www.facebook.com/live/producer', window }, null, b, now);
  assert.equal((await close(10)).ok, false);
  assert.equal((await close(11)).ok, false);
  assert.equal((await close(12)).ok, false);
  assert.equal((await close(99)).ok, false);                                 // no such window
  assert.deepEqual(await close(9), { ok: true, window: 9 });
  assert.deepEqual(b.did, [['remove', 9]]);
});

test('finding a page the hub just opened remembers it and moves nothing', async () => {
  const b = browser([{ id: 3, type: 'app', tabs: [tab(30, TIKTOK)] }, { id: 9, type: 'app', tabs: [tab(90, TIKTOK)] }]);
  assert.deepEqual(await W.job({ action: 'find', role: 'tiktok', url: TIKTOK, known: [3], wait: 30 }, null, b, now), { ok: true, window: 9 });
  assert.deepEqual(b.did, []);
  assert.equal((await W.job({ action: 'find', role: 'chat' }, null, b, now)).ok, false);   // (the chat window isn't found this way)
});

test('without a recorded window, closing takes the window at the exact address the hub opened', async () => {
  const b = browser([
    { id: 9, type: 'app', tabs: [tab(90, 'https://rumble.com/chat/popup/42')] },
    { id: 10, type: 'app', tabs: [tab(100, 'https://rumble.com/chat/popup/7')] },     // another live's chat
  ]);
  assert.deepEqual(await W.job({ action: 'close', role: 'rumble', url: 'https://rumble.com/chat/popup/42' }, null, b, now), { ok: true, window: 9 });
  assert.deepEqual(b.did, [['remove', 9]]);
});

test("each role's address is its own site, and no further", () => {
  const ours = (role, url, type = 'app') => W.ours({ type, tabs: [{ url }] }, role);
  assert.ok(ours('chat', CHAT) && ours('chat', CHAT + '?dry') && !ours('chat', CHAT + 'studio') && !ours('chat', 'http://localhost:4466/'));
  assert.ok(ours('x', 'https://studio.x.com/live') && !ours('x', 'https://x.com/home'));
  assert.ok(ours('facebook', 'https://www.facebook.com/live/producer') && !ours('facebook', 'https://www.facebook.com/messages'));
  assert.ok(ours('instagram', 'https://www.instagram.com/') && !ours('instagram', 'https://www.instagram.com/direct/inbox/'));
  assert.ok(ours('rumble', 'https://rumble.com/chat/popup/1') && !ours('rumble', 'https://rumble.com/'));
  assert.ok(ours('tiktok', TIKTOK) && !ours('tiktok', TIKTOK, 'normal') && !ours('tiktok', TIKTOK, 'popup'));
  assert.ok(!W.ours({ type: 'app', tabs: [{ url: TIKTOK }, { url: TIKTOK }] }, 'tiktok'));
  assert.ok(!ours('toString', TIKTOK) && !ours('constructor', TIKTOK));
});

test('a place must be a real rectangle', async () => {
  for (const box of [null, [1, 2, 3], [1, 2, 0, 400], [1, 2, 300, 10], ['1', 2, 300, 400], [1.5, 2, 300, 400], [1e9, 0, 300, 400]]) {
    assert.equal(W.bounds(box), null, JSON.stringify(box));
  }
  assert.deepEqual(W.bounds([-1920, 0, 460, 1080]), { left: -1920, top: 0, width: 460, height: 1080 });   // a screen to the left
  const b = everyday();
  assert.equal((await W.job({ action: 'place', role: 'chat', box: [1, 2] }, { id: 50, windowId: 5 }, b, now)).ok, false);
  assert.deepEqual(b.did, []);
});

test("the browser's own refusal is passed on", async () => {
  const b = everyday();
  b.update = async () => { throw new Error('Invalid value for bounds. Bounds must be at least 50% within visible screen space.'); };
  const answer = await W.job({ action: 'place', role: 'chat', box: BOX }, { id: 50, windowId: 5 }, b, now);
  assert.equal(answer.ok, false);
  assert.match(answer.why, /visible screen space/);
});

test('listing gives only window ids, of every ordinary kind of window', async () => {
  const b = browser([{ id: 2, type: 'normal', tabs: [] }, { id: 4, type: 'app', tabs: [] }, { id: 6, type: 'devtools', tabs: [] }]);
  assert.deepEqual(await W.job({ action: 'list' }, null, b, now), { ok: true, windows: [2, 4] });
});
