// On the streamer's own TikTok LIVE page (CrossChat opens it when OBS goes live), this script:
//   - passes new chat lines, gifts, follows, shares, likes (and joins, when the streamer wants them) and the viewer
//     count to the CrossChat hub on this PC, which shows them in the CrossChat window and as alerts;
//   - types a reply that comes from that window into TikTok's own chat box and sends it.
// It first asks the hub which TikTok account is the streamer's. On every other TikTok page, someone else's LIVE
// included, it reads nothing and sends nothing. It never touches the TikTok login.
(() => {
  const { sleep, clean, ask, hash, waitFor, sendLines } = globalThis.CrossChatCommon;
  const { classify, giftStreaks } = globalThis.CrossChatTikTokRows;

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
      await sendLines('tt-feed', { page: pageName(), viewers: viewers() }, fresh(Date.now()).concat(outbox.slice()), (l) => {
        if (l.node) told.set(l.node, l.sig);
        else { const at = outbox.indexOf(l); if (at >= 0) outbox.splice(at, 1); }
      });
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
    return (await waitFor(() => !box.isConnected || clean(box.textContent) === '', 5000, 200)) ? { ok: true } : { ok: false, why: 'TikTok did not send it' };
  }

  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (message.type !== 'tt-say') return;
    say(String(message.text || '')).then(respond, () => respond({ ok: false, why: 'it failed' }));
    return true;   // the answer comes later
  });
  setInterval(tick, 1000);
})();
