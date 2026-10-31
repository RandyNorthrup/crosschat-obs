// On the streamer's own TikTok LIVE page (CrossChat opens it when OBS goes live), this script:
//   - passes new chat lines and the viewer count to the CrossChat hub on this PC, which shows them in the
//     CrossChat window;
//   - types a reply that comes from that window into TikTok's own chat box and sends it.
// It first asks the hub which TikTok account is the streamer's. On every other TikTok page, someone else's LIVE
// included, it reads nothing and sends nothing. It never touches the TikTok login.
(() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const ask = (type, data) => new Promise((r) => {
    try { chrome.runtime.sendMessage({ type, data }, (a) => r(chrome.runtime.lastError ? null : a)); } catch (e) { r(null); }
  });
  const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim();
  const pageName = () => ((/^\/@([^/?#]+)\/live/.exec(location.pathname) || [])[1] || '').toLowerCase();
  const told = new WeakSet();                 // chat lines already passed on
  let streamer = '', checkedAt = 0, wasMine = false, busy = false;

  // The streamer's own page, while the hub says a stream is on.
  async function mine() {
    if (!pageName()) return false;            // not a LIVE page at all: nothing to ask
    if (Date.now() - checkedAt > 15000) {
      checkedAt = Date.now();
      const answer = await ask('tt-check');
      streamer = answer && answer.live ? String(answer.tiktok || '').toLowerCase() : '';
    }
    return !!streamer && pageName() === streamer;
  }

  // One chat line: who, and what came after their name (text, and TikTok's own emoji by their names).
  function line(node) {
    const owner = node.querySelector('[data-e2e="message-owner-name"]');
    if (!owner) return null;
    const name = clean(owner.getAttribute('title') || owner.textContent);
    let said = '';
    const walk = document.createTreeWalker(node, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      if (owner.contains(n) || !(owner.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
      if (n.nodeType === Node.TEXT_NODE) said += n.nodeValue;
      else if (n.tagName === 'IMG' && n.alt) said += n.alt;
    }
    return name && clean(said) ? { name, text: clean(said) } : null;
  }

  function hash(s) {
    let h = 5381;
    for (let i = 0; i < s.length; i++) h = ((h * 33) ^ s.charCodeAt(i)) >>> 0;
    return h.toString(36);
  }

  // The streamer's own name as the page shows it, so their own lines can be marked as theirs.
  const hostName = () => clean((document.querySelector('[data-e2e="room-header-anchor-name"]') || {}).textContent);

  // "Viewers · 1.2K" at the top of the chat, as a number, or ''.
  function viewers() {
    for (const el of document.querySelectorAll('[data-e2e="live-chat-container"] *, [data-e2e="public-screen-container"] *')) {
      if (el.children.length > 4) continue;
      const m = /^Viewers\s*·\s*([\d.,]+)\s*([KM])?/i.exec(clean(el.textContent));
      if (m) return String(Math.round(parseFloat(m[1].replace(/,/g, '')) * ({ K: 1e3, M: 1e6 }[(m[2] || '').toUpperCase()] || 1)));
    }
    return '';
  }

  // New lines since last time. TikTok gives them no ids, so one is made from who said what and how many times they
  // said it so far; the hub uses it to skip lines it already has (after a reload of this page, say).
  function fresh() {
    const out = [], times = {}, host = hostName();
    for (const node of document.querySelectorAll('[data-e2e="chat-message"]')) {
      const l = line(node);
      if (!l) continue;
      const key = l.name + '\n' + l.text;
      times[key] = (times[key] || 0) + 1;
      if (!told.has(node)) out.push({ node, id: hash(key) + 'n' + times[key], name: l.name.slice(0, 60), text: l.text.slice(0, 300), host: !!host && l.name === host });
    }
    return out;
  }

  async function tick() {
    if (busy) return;
    busy = true;
    try {
      if (!(await mine())) {
        if (wasMine) { wasMine = false; await ask('tt-feed', { page: pageName() || streamer, over: 1 }); }
        return;
      }
      wasMine = true;
      const lines = fresh();
      do {                                     // in batches small enough for one request (a burst of emoji is large)
        const batch = [];
        while (lines.length && (!batch.length || encodeURIComponent(JSON.stringify(batch.concat(lines[0]).map(({ node, ...l }) => l))).length < 6000)) {
          batch.push(lines.shift());
        }
        const answer = await ask('tt-feed', { page: pageName(), viewers: viewers(), lines: JSON.stringify(batch.map(({ node, ...l }) => l)) });
        if (!answer || !answer.reached || !answer.data || !answer.data.mine) break;   // tried again next time
        batch.forEach((l) => told.add(l.node));
      } while (lines.length);
    } finally {
      busy = false;
    }
  }

  async function say(text) {
    const box = document.querySelector('[data-e2e="room-chat-input-field"]');
    if (!(await mine()) || !box) return { ok: false, why: 'the TikTok LIVE page is not open' };
    box.focus();
    document.execCommand('selectAll', false);
    document.execCommand('insertText', false, text);
    await sleep(200);
    const send = document.querySelector('[data-e2e="room-chat-send-btn"]');
    if (!send || send.disabled || send.getAttribute('aria-disabled') === 'true') return { ok: false, why: 'TikTok would not take the message' };
    send.click();
    for (let i = 0; i < 25; i++) {
      await sleep(200);
      if (!box.isConnected || clean(box.textContent) === '') return { ok: true };
    }
    return { ok: false, why: 'TikTok did not send it' };
  }

  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (message.type !== 'tt-say') return;
    say(String(message.text || '')).then(respond, () => respond({ ok: false, why: 'it failed' }));
    return true;   // the answer comes later
  });
  setInterval(tick, 1000);
})();
