// CrossChat's own windows, for the hub (hub/hub.py): the chat window, and the platform pages the hub opens with the
// browser's --app switch (X Live Studio, your TikTok LIVE page, Live Producer, Instagram, Rumble's chat pop-out). The
// hub asks through the chat window (bridge.js) for one of them to be placed, moved or closed, and the browser's own
// window API does it: the same on Windows, macOS and Linux, with no permission from the system (macOS refuses Apple
// Events to programs OBS starts; a Wayland desktop lets no program move another's windows). chrome.windows needs no
// extension permission either.
//
// Nothing else is ever touched. A window counts as CrossChat's only while it is a bare --app window (type "app") with
// a single tab at its role's address (PLACES below; the extension can read a tab's address only on the sites it may
// work on), and then only:
//   - the chat window: the window of the chat page that asked when it is one, else the newest; for closing, every one;
//   - a platform page: the window the hub recorded when it opened it, or else one at the exact address the hub opened
//     that wasn't open before the hub opened it (`known`: the windows open just before).
// A tab of yours at any of these addresses is in an ordinary window (type "normal") and is never moved or closed.
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;   // Node (the tests)
  else root.CrossChatWindows = api;
})(typeof self !== 'undefined' ? self : globalThis, function () {
  const HUB = 'http://127.0.0.1:4466';
  const PLACES = {
    chat: (u) => u.origin === HUB && u.pathname === '/',
    x: (u) => u.origin === 'https://studio.x.com',
    tiktok: (u) => u.origin === 'https://www.tiktok.com',
    facebook: (u) => u.origin === 'https://www.facebook.com' && u.pathname.startsWith('/live/producer'),
    instagram: (u) => u.origin === 'https://www.instagram.com' && u.pathname === '/',
    rumble: (u) => u.origin === 'https://rumble.com' && u.pathname.startsWith('/chat/popup/'),
  };
  const TYPES = ['normal', 'popup', 'app'];   // every kind of window a person uses (not DevTools)
  const LONGEST_WAIT = 30;                     // seconds a window the hub has just opened is looked for
  const CLOSE_DELAY = 800;                     // ms: the chat window closes once its answer has left it
  const SETTLE = 400, PLACE_TRIES = 3;         // ms before a placed window is looked at again; placings at most
  const FAR = 100000, SMALLEST = 50;

  const pause = (ms) => new Promise((done) => setTimeout(done, ms));
  function address(text) { try { return text ? new URL(text) : null; } catch (e) { return null; } }
  const shown = (tab) => address(tab.url || tab.pendingUrl);
  const site = (role) => (Object.prototype.hasOwnProperty.call(PLACES, role) ? PLACES[role] : null);   // (never "toString" and the like)

  // Whether `win` is one of CrossChat's windows for `role` (see above).
  function ours(win, role) {
    const isSite = site(role);
    if (!isSite || !win || win.type !== 'app' || !Array.isArray(win.tabs) || win.tabs.length !== 1) return false;
    const at = shown(win.tabs[0]);
    return !!at && isSite(at);
  }

  // Whether a tab is at the address the hub opened (or a page under it), whatever its query or #fragment now says.
  function opened(tab, url) {
    return [tab.url, tab.pendingUrl].some((text) => {
      const at = address(text);
      return !!at && at.origin === url.origin && (at.pathname === url.pathname || at.pathname.startsWith(url.pathname.replace(/\/?$/, '/')));
    });
  }

  // The hub's [x, y, width, height] as the browser wants it, or null.
  function bounds(box) {
    if (!Array.isArray(box) || box.length !== 4 || !box.every(Number.isInteger)) return null;
    const [left, top, width, height] = box;
    if (Math.abs(left) > FAR || Math.abs(top) > FAR || width < SMALLEST || height < SMALLEST || width > FAR || height > FAR) return null;
    return { left, top, width, height };
  }

  const all = (windows) => windows.getAll({ populate: true, windowTypes: TYPES });
  const one = (windows, id) => windows.get(id, { populate: true, windowTypes: TYPES }).catch(() => null);

  // The chat window: the one the asking page is in, when that is one of CrossChat's; else the newest of CrossChat's
  // (the page that asked can be the chat in a tab of yours, whose window is never moved).
  async function chatWindow(tab, windows) {
    if (tab && typeof tab.windowId === 'number') {
      const win = await one(windows, tab.windowId);
      if (ours(win, 'chat') && win.tabs[0].id === tab.id) return win;
    }
    return (await all(windows)).filter((w) => ours(w, 'chat')).sort((a, b) => b.id - a.id)[0] || null;
  }

  // A platform page's window: the one the hub recorded, else the newest new one at the address it opened, looked for
  // for up to `wait` seconds while it opens.
  async function pageWindow(data, role, windows, sleep, patient) {
    const id = Number(data.window) || 0;
    if (id) {
      const win = await one(windows, id);
      return ours(win, role) ? win : null;
    }
    const url = address(data.url);
    if (!url || !site(role)(url)) return null;            // the hub always names an address of that role's own site
    const before = new Set(Array.isArray(data.known) ? data.known : []);
    const until = Date.now() + (patient ? Math.min(Math.max(Number(data.wait) || 0, 0), LONGEST_WAIT) * 1000 : 0);
    for (;;) {
      const found = (await all(windows)).filter((w) => !before.has(w.id) && ours(w, role) && opened(w.tabs[0], url))
        .sort((a, b) => b.id - a.id)[0];
      if (found || Date.now() >= until) return found || null;
      await sleep(250);
    }
  }

  // A window that has only just opened can still be given its first size by the desktop after ours (seen on Wayland,
  // with KWin): so the window is looked at again a moment later, and placed again if its size didn't take. A desktop
  // can also keep a window maximized one way, which the browser doesn't see (KWin through XWayland, with a window that
  // opened as tall as the screen, keeps its top and height): before the last try the window is maximized and made
  // normal again, which ends that.
  async function put(windows, win, where, sleep) {
    if (win.state !== 'normal') await windows.update(win.id, { state: 'normal' });   // (a minimized or maximized one takes no bounds)
    for (let attempt = 1; ; attempt++) {
      await windows.update(win.id, where);
      await sleep(SETTLE);
      const now = await one(windows, win.id);
      if (!now || (now.width === where.width && now.height === where.height) || attempt >= PLACE_TRIES) return;
      if (attempt === PLACE_TRIES - 1) {              // (each step has to land before the next: seen with KWin)
        await windows.update(win.id, { state: 'maximized' });
        await sleep(SETTLE);
        await windows.update(win.id, { state: 'normal' });
        await sleep(SETTLE);
      }
    }
  }

  // One job from the hub: { action: "list" | "place" | "find" | "close", role, url, box, window, known, wait }. `tab` is the
  // chat page's tab that passed it on; `windows` is chrome.windows. Answers { ok, window } or { ok: false, why }.
  async function job(data, tab, windows, sleep = pause) {
    const action = String(data.action || ''), role = String(data.role || '');
    try {
      if (action === 'list') return { ok: true, windows: (await windows.getAll({ windowTypes: TYPES })).map((w) => w.id) };
      if (!site(role)) return { ok: false, why: "that is not one of CrossChat's windows" };
      if (action === 'place') {
        const where = bounds(data.box);
        if (!where) return { ok: false, why: 'no place to put it' };
        const win = role === 'chat' ? await chatWindow(tab, windows) : await pageWindow(data, role, windows, sleep, true);
        if (!win && role === 'chat') return { ok: false, why: 'no chat window is open', none: true };   // (in this browser: the hub opens one)
        if (!win) return { ok: false, why: 'the window is not open' };
        await put(windows, win, where, sleep);
        return { ok: true, window: win.id };
      }
      if (action === 'find' && role !== 'chat') {      // a page the hub just opened, found (and remembered) but not moved
        const win = await pageWindow(data, role, windows, sleep, true);
        return win ? { ok: true, window: win.id } : { ok: false, why: 'the window is not open' };
      }
      if (action === 'close') {
        if (role === 'chat') {
          const wins = (await all(windows)).filter((w) => ours(w, 'chat'));
          sleep(CLOSE_DELAY).then(() => Promise.all(wins.map((w) => windows.remove(w.id).catch(() => null))));
          return { ok: true, windows: wins.map((w) => w.id) };
        }
        const win = await pageWindow(data, role, windows, sleep, false);
        if (!win) return { ok: false, why: 'the window is not open' };
        await windows.remove(win.id);
        return { ok: true, window: win.id };
      }
      return { ok: false, why: 'unknown window job' };
    } catch (e) {
      return { ok: false, why: String((e && e.message) || e).slice(0, 200) };   // the browser's reason (a place off every screen, say)
    }
  }

  return { job, ours, opened, bounds, PLACES, TYPES, LONGEST_WAIT, CLOSE_DELAY, PLACE_TRIES };
});
