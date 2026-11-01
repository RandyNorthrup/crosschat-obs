// On the streamer's own TikTok LIVE page (CrossChat opens it when OBS goes live), this script:
//   - passes new chat lines, gifts, follows, shares, likes (and joins, when the streamer wants them) and the viewer
//     count to the CrossChat hub on this PC, which shows them in the CrossChat window and as alerts;
//   - types a reply that comes from that window into TikTok's own chat box and sends it.
// It first asks the hub which TikTok account is the streamer's. On every other TikTok page, someone else's LIVE
// included, it reads nothing and sends nothing. It never touches the TikTok login.
(() => {
  const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim();

  // ---- what one row of TikTok's chat list is (no page access here, so the tests can run it in Node) ----------------
  // TikTok marks its own rows (gifts, follows, shares, likes, joins) apart from what viewers type, by data-e2e name
  // or class name. A row only counts as one of those when it is marked so: a viewer who types "followed the host" or
  // "×99" in chat stays a chat line and can't fake an alert. And a chat row's words are never dropped: one that is
  // marked but isn't a known event still shows as chat.
  const MARKED = /(social|system|gift|enter|like|share|follow)-?message/i;
  const ACTIONS = [
    ['follow', /^followed\b/i],
    ['share', /^shared\b/i],
    ['like', /^(liked|tapped)\b/i],
    ['join', /^joined\b/i],
  ];

  // row: { e2e, hints (class names), name (from the name element, may be ''), rest (what follows the name),
  //        giftImage (a TikTok gift picture is in the row), giftAlt (that picture's name), giftCount (its count text) }
  // Answers { kind: 'chat', name, text } | { kind: 'gift', name, gift, count } | { kind: follow|share|like|join, name,
  // count } | null (a TikTok notice that is none of these, such as its welcome line).
  function classify(row) {
    const e2e = String(row.e2e || ''), hints = String(row.hints || '');
    let name = clean(row.name), rest = clean(row.rest);
    const marked = e2e !== 'chat-message' || MARKED.test(hints);
    if (!name && marked) {                          // no name element: "lofi.leo followed the host"
      const m = /^(.{1,60}?)\s+(followed|shared|liked|tapped|joined|sent|gifted)\b/i.exec(rest);
      if (m) { name = m[1]; rest = rest.slice(m[1].length).trim(); }
    }
    if (!name) return null;
    name = name.slice(0, 60);
    const chat = () => (e2e === 'chat-message' && rest ? { kind: 'chat', name, text: rest.slice(0, 300) } : null);
    if (!marked) return chat();
    if (/gift/i.test(e2e) || /gift-?message/i.test(hints)) {
      const counted = /[x×]\s*(\d{1,5})\s*$/i.exec(rest) || /[x×]?\s*(\d{1,5})/i.exec(clean(row.giftCount));
      if (!counted && !row.giftImage) return chat();
      const said = clean(rest.replace(/[x×]\s*\d{1,5}\s*$/i, '').replace(/^(has\s+)?(sent|gifted|send)\b\s*/i, ''));
      const gift = (said || clean(row.giftAlt) || 'a gift').slice(0, 40);
      return { kind: 'gift', name, gift, count: counted ? Math.max(1, parseInt(counted[1], 10)) : 1 };
    }
    for (const [kind, pattern] of ACTIONS) {
      if (!pattern.test(rest)) continue;
      const n = /[x×]\s*(\d{1,5})/i.exec(rest) || /(\d{1,5})\s+likes?\b/i.exec(rest);
      return { kind, name, count: n ? Math.max(1, parseInt(n[1], 10)) : 1 };
    }
    return chat();
  }

  function hash(s) {
    let h = 5381;
    for (let i = 0; i < s.length; i++) h = ((h * 33) ^ s.charCodeAt(i)) >>> 0;
    return h.toString(36);
  }

  // One gift streak is one alert: TikTok raises a combo's count (×1, ×2 … ×30) in the same row or in new rows, so a
  // streak is held until its count has stopped rising for GIFT_QUIET ms and then passed on once, with the last count.
  // A combo whose own row rises again after that (a slow tapper) is passed on as the gifts added since, never counted
  // twice. slot: the row the count is shown in.
  const GIFT_QUIET = 4500, GIFT_AGAIN = 30000;
  function giftStreaks(emit) {
    const open = new Map();                         // name + gift -> { g, count, base, slot, last }
    const done = new Map();                         // name + gift -> { count, slot, at } of the streak passed on last
    const close = (key, s, now) => {
      open.delete(key);
      done.set(key, { count: s.count, slot: s.slot, at: now });
      if (done.size > 500) done.delete(done.keys().next().value);
      emit(s.g, s.count - s.base);
    };
    return {
      see(g, now, slot) {
        const key = g.name + '\n' + g.gift, s = open.get(key);
        if (s && g.count > s.count) { s.count = g.count; s.slot = slot; s.last = now; return; }
        if (s) close(key, s, now);                  // the same gift again from a lower count: the earlier streak is over
        const before = done.get(key);
        const again = before && slot !== undefined && before.slot === slot && now - before.at < GIFT_AGAIN && g.count > before.count;
        open.set(key, { g, count: g.count, base: again ? before.count : 0, slot, last: now });
      },
      flush(now, all) {
        for (const [key, s] of open) if (all || now - s.last >= GIFT_QUIET) close(key, s, now);
      },
    };
  }

  if (typeof module === 'object' && module.exports) {      // Node (the tests): the parts above, nothing else
    module.exports = { classify, giftStreaks, GIFT_QUIET, GIFT_AGAIN };
    return;
  }

  // ---- on the page ---------------------------------------------------------------------------------------------------
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const ask = (type, data) => new Promise((r) => {
    try { chrome.runtime.sendMessage({ type, data }, (a) => r(chrome.runtime.lastError ? null : a)); } catch (e) { r(null); }
  });
  const pageName = () => ((/^\/@([^/?#]+)\/live/.exec(location.pathname) || [])[1] || '').toLowerCase();
  // TikTok reuses a row's element for a later line, so a row counts as new whenever what it shows has changed.
  const told = new WeakMap();                  // row -> what it showed when passed on
  const outbox = [];                           // gifts, follows, shares, likes and joins not yet taken by the hub
  const visit = Date.now().toString(36);       // keeps this page's ids apart from those of an earlier visit
  let streamer = '', joins = false, checkedAt = 0, wasMine = false, busy = false, made = 0;
  const streaks = giftStreaks((g, count) => queue({ kind: 'gift', name: g.name, gift: g.gift, count }));

  // The streamer's own page, while the hub says a stream is on.
  async function mine() {
    if (!pageName()) return false;            // not a LIVE page at all: nothing to ask
    if (Date.now() - checkedAt > 15000) {
      checkedAt = Date.now();
      const answer = await ask('tt-check');
      streamer = answer && answer.live ? String(answer.tiktok || '').toLowerCase() : '';
      joins = !!(answer && answer.joins);
    }
    return !!streamer && pageName() === streamer;
  }

  const giftPicture = (img) => /tiktokcdn|ibyteimg|byteimg|webcast/i.test(img.getAttribute('src') || '') && !img.closest('[data-e2e="message-owner-name"]');

  // A row's parts: who (the name element), and what came after it: text, TikTok's emoji by their names, and a gift
  // picture apart (its name, when it has one, is the gift's).
  function parts(node) {
    const owner = node.querySelector('[data-e2e="message-owner-name"]');
    const row = { e2e: node.getAttribute('data-e2e') || '', name: owner ? clean(owner.getAttribute('title') || owner.textContent) : '',
                  rest: '', giftImage: false, giftAlt: '', giftCount: '' };
    row.hints = [node, ...node.querySelectorAll('[class]')].slice(0, 40).map((e) => String(e.className || '')).join(' ');
    const counter = node.querySelector('[class*="GiftCount"], [class*="gift-count"]');
    if (counter) row.giftCount = counter.textContent;
    const walk = document.createTreeWalker(node, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      if (owner && (owner.contains(n) || !(owner.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING))) continue;
      if (n.nodeType === Node.TEXT_NODE) row.rest += n.nodeValue;
      else if (n.tagName === 'IMG' && (/gift/i.test(row.e2e) || /gift-?message/i.test(row.hints)) && giftPicture(n)) {
        row.giftImage = true;
        row.giftAlt = row.giftAlt || clean(n.alt);
      }
      else if (n.tagName === 'IMG' && n.alt) row.rest += n.alt;
    }
    return row;
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

  function queue(item) {
    outbox.push({ id: visit + 'e' + (++made).toString(36), ...item });
    if (outbox.length > 500) outbox.splice(0, outbox.length - 500);
  }

  const ROWS = '[data-e2e="chat-message"], [data-e2e="social-message"], [data-e2e="enter-message"], [data-e2e="gift-message"], '
    + '[data-e2e="like-message"], [data-e2e="share-message"], [data-e2e="follow-message"]';

  // New chat lines since last time, and new TikTok events into the outbox. Chat lines have no ids on TikTok's page, so
  // one is made from who said what and how many times they said it so far; the hub uses it to skip lines it already
  // has (after a reload of this page, say).
  function fresh(now) {
    const out = [], times = {}, host = hostName();
    for (const node of document.querySelectorAll(ROWS)) {
      const r = classify(parts(node));
      if (!r) continue;
      if (r.kind === 'chat') {
        const key = r.name + '\n' + r.text;
        times[key] = (times[key] || 0) + 1;
        if (told.get(node) !== key) out.push({ node, sig: key, id: hash(key) + 'n' + times[key], name: r.name, text: r.text, host: !!host && r.name === host });
        continue;
      }
      const sig = JSON.stringify(r);
      if (told.get(node) === sig) continue;
      told.set(node, sig);
      if (host && r.name === host) continue;   // the streamer's own likes or shares aren't alerts
      if (r.kind === 'gift') streaks.see(r, now, node);
      else if (r.kind !== 'join' || joins) queue(r);
    }
    streaks.flush(now, false);
    return out;
  }

  async function tick() {
    if (busy) return;
    busy = true;
    try {
      if (!(await mine())) {
        if (wasMine) {
          wasMine = false;
          streaks.flush(Date.now(), true);
          outbox.length = 0;
          await ask('tt-feed', { page: pageName() || streamer, over: 1 });
        }
        return;
      }
      wasMine = true;
      const lines = fresh(Date.now()).concat(outbox.slice());
      const size = (list) => encodeURIComponent(JSON.stringify(list.map(({ node, sig, ...l }) => l))).length;
      do {                                     // in batches small enough for one request (a burst of emoji is large)
        const batch = [];
        while (lines.length && batch.length < 50 && (!batch.length || size(batch.concat(lines[0])) < 6000)) batch.push(lines.shift());
        const answer = await ask('tt-feed', { page: pageName(), viewers: viewers(), lines: JSON.stringify(batch.map(({ node, sig, ...l }) => l)) });
        if (!answer || !answer.reached || !answer.data || !answer.data.mine) break;   // tried again next time
        batch.forEach((l) => {
          if (l.node) told.set(l.node, l.sig);
          else { const at = outbox.indexOf(l); if (at >= 0) outbox.splice(at, 1); }
        });
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
