// On instagram.com (CrossChat opens its home page when OBS goes live, and Instagram's Live producer opens over it from
// Create → Live video), this script, while a live is running and CrossChat says Instagram is on:
//   - passes new comments and the viewer count to the CrossChat hub on this PC, which shows them in the CrossChat
//     window;
//   - types a reply that comes from that window into the live's comment box and posts it.
// The Live producer only ever shows the signed-in streamer's own live. The script reads nothing else on Instagram
// (no feed, no messages, no profiles) and never touches the Instagram login.
(() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const ask = (type, data) => new Promise((r) => {
    try { chrome.runtime.sendMessage({ type, data }, (a) => r(chrome.runtime.lastError ? null : a)); } catch (e) { r(null); }
  });
  const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim();
  const told = new WeakSet();                 // comments already passed on
  let on = false, checkedAt = 0, wasLive = false, busy = false;

  // The Live producer while a live runs: a dialog with the video and the Comments / Event Log tabs. (Before going live
  // it shows the stream key instead of the tabs, and after the end only the recording.)
  const producer = () => [...document.querySelectorAll('[role="dialog"]')].find((d) => d.querySelector('[role="tablist"]') && d.querySelector('video')) || null;

  async function wanted() {
    if (Date.now() - checkedAt > 15000) {
      checkedAt = Date.now();
      const answer = await ask('ig-check');
      on = !!(answer && answer.instagram && answer.live);
    }
    return on && !!producer();
  }

  function hash(s) {
    let h = 5381;
    for (let i = 0; i < s.length; i++) h = ((h * 33) ^ s.charCodeAt(i)) >>> 0;
    return h.toString(36);
  }

  // One comment: a button holding the commenter's picture, then their name, then what they wrote.
  function comment(row) {
    const parts = [];
    const walk = document.createTreeWalker(row, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      if (n.parentElement.closest('svg')) continue;      // icon titles such as "Verified"
      const t = clean(n.nodeValue);
      if (t) parts.push(t);
    }
    const name = parts.shift() || '';
    const text = clean(parts.join(' '));
    return name && text ? { name, text } : null;
  }

  // The comment rows: buttons in the producer with a picture in them (its own controls have only icons).
  function rows(dialog) {
    return [...dialog.querySelectorAll('[role="button"]')].filter((b) => b.querySelector('img') && !b.querySelector('textarea, [role="button"], video')
      && !b.closest('footer, [role="contentinfo"], [role="tablist"]'));
  }

  // The signed-in account (the streamer): the name on the "Profile" link of Instagram's own menu, so their comments
  // can be marked as theirs. '' when it can't be told.
  function hostName() {
    for (const a of document.querySelectorAll('a[href^="/"]')) {
      if (/^Profile$/i.test(clean(a.textContent)) && a.querySelector('img')) return ((/^\/([\w.]{1,30})\/?$/.exec(a.getAttribute('href')) || [])[1] || '');
    }
    return '';
  }

  // The number beside the viewer-count icon on the video, or ''.
  function viewers(dialog) {
    const icon = dialog.querySelector('[aria-label="Viewer count icon"]');
    for (let box = icon && icon.parentElement, up = 0; box && up < 3; box = box.parentElement, up++) {
      const m = /([\d.,]+)\s*([KM])?$/i.exec(clean(box.textContent));
      if (m) return String(Math.round(parseFloat(m[1].replace(/,/g, '')) * ({ K: 1e3, M: 1e6 }[(m[2] || '').toUpperCase()] || 1)));
    }
    return '';
  }

  // New comments since last time. Instagram gives them no ids on the page, so one is made from who said what and how
  // many times they said it so far; the hub uses it to skip comments it already has (when the tab is switched back
  // from the Event Log, say, which draws them all again).
  function fresh(dialog) {
    const out = [], times = {}, host = hostName();
    for (const row of rows(dialog)) {
      const c = comment(row);
      if (!c) continue;
      const key = c.name + '\n' + c.text;
      times[key] = (times[key] || 0) + 1;
      if (!told.has(row)) out.push({ node: row, id: hash(key) + 'n' + times[key], name: c.name.slice(0, 60), text: c.text.slice(0, 1000), host: !!host && c.name === host });
    }
    return out;
  }

  async function tick() {
    if (busy) return;
    busy = true;
    try {
      if (!(await wanted())) {
        if (wasLive) { wasLive = false; await ask('ig-feed', { over: 1 }); }
        return;
      }
      wasLive = true;
      const dialog = producer();
      const lines = fresh(dialog);
      do {                                     // in batches small enough for one request
        const batch = [];
        while (lines.length && (!batch.length || encodeURIComponent(JSON.stringify(batch.concat(lines[0]).map(({ node, ...l }) => l))).length < 6000)) {
          batch.push(lines.shift());
        }
        const answer = await ask('ig-feed', { viewers: viewers(dialog), lines: JSON.stringify(batch.map(({ node, ...l }) => l)) });
        if (!answer || !answer.reached || !answer.data || !answer.data.mine) break;   // tried again next time
        batch.forEach((l) => told.add(l.node));
      } while (lines.length);
    } finally {
      busy = false;
    }
  }

  // The comment box takes Enter to post (the paper plane beside it shares the live instead, so it is never pressed).
  async function say(text) {
    const dialog = producer();
    const box = dialog && dialog.querySelector('textarea');
    if (!(await wanted()) || !box) return { ok: false, why: 'no Instagram live is running in this browser' };
    box.focus();
    box.select();
    if (!document.execCommand('insertText', false, text) || box.value !== text) {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(box, text);
      box.dispatchEvent(new Event('input', { bubbles: true }));
    }
    await sleep(200);
    for (const type of ['keydown', 'keypress', 'keyup']) {
      box.dispatchEvent(new KeyboardEvent(type, { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true }));
    }
    for (let i = 0; i < 25; i++) {
      await sleep(200);
      if (!box.isConnected || box.value === '') return { ok: true };
    }
    return { ok: false, why: 'Instagram did not post it' };
  }

  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (message.type !== 'ig-say') return;
    say(String(message.text || '')).then(respond, () => respond({ ok: false, why: 'it failed' }));
    return true;   // the answer comes later
  });
  setInterval(tick, 1000);
})();
