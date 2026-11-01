// On Facebook's Live Producer (where a Facebook live is started and ended; CrossChat opens it when OBS goes live), this
// script, while a live is running and CrossChat says Facebook is on:
//   - passes new comments and the viewer count to the CrossChat hub on this PC, which shows them in the CrossChat
//     window;
//   - types a reply that comes from that window into Live Producer's comment box and posts it.
// Live Producer only ever shows the signed-in streamer's own broadcasts. The extension may touch no other part of
// Facebook, and it never touches the Facebook login.
(() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const ask = (type, data) => new Promise((r) => {
    try { chrome.runtime.sendMessage({ type, data }, (a) => r(chrome.runtime.lastError ? null : a)); } catch (e) { r(null); }
  });
  const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim();
  const told = new WeakSet();                 // comments already passed on
  let on = false, checkedAt = 0, wasLive = false, busy = false;

  // A live is running: Live Producer then shows its "End live video" button.
  const live = () => [...document.querySelectorAll('[role="button"], button')].some((b) => /^End live video$/i.test(clean(b.getAttribute('aria-label') || b.textContent)));

  async function wanted() {
    if (Date.now() - checkedAt > 15000) {
      checkedAt = Date.now();
      const answer = await ask('fb-check');
      on = !!(answer && answer.facebook && answer.live);
    }
    return on && live();
  }

  // One comment: Facebook marks each as an article whose first link (the author's name) carries the comment's own id.
  function comment(article) {
    const link = article.querySelector('a[href*="comment_id="]');
    if (!link) return null;                   // still posting: it gets its id in a moment
    const id = new URL(link.href, location.href).searchParams.get('comment_id') || '';
    const name = clean(link.textContent);
    let text = '';
    const walk = document.createTreeWalker(article, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      if (n.nodeType === Node.ELEMENT_NODE) {
        if (n.tagName === 'IMG' && n.alt && !n.closest('a, [role="button"]')) text += n.alt;     // emoji
        continue;
      }
      if (!n.parentElement.closest('a, [role="button"], button')) text += n.nodeValue;
    }
    text = clean(text).replace(/\s*Posting(…|\.\.\.)$/i, '');     // Facebook's own "Posting…" under a fresh comment
    return id && name && text ? { id, name, text } : null;
  }

  // The streamer's own name, from the "<name> is live now." line, so their own comments can be marked.
  function hostName() {
    for (const el of document.querySelectorAll('span, div')) {
      if (el.children.length < 4 && /^is live now\.?$/i.test(clean(el.textContent))) {
        const prev = el.previousElementSibling || (el.parentElement && el.parentElement.querySelector('a'));
        if (prev) return clean(prev.textContent);
      }
    }
    return '';
  }

  // The number under "Current viewers", or ''.
  function viewers() {
    for (const el of document.querySelectorAll('span, div')) {
      if (el.children.length < 3 && /^Current viewers$/i.test(clean(el.textContent))) {
        for (let box = el.parentElement, up = 0; box && up < 4; box = box.parentElement, up++) {   // the number sits beside it
          const m = /^Current viewers\s*([\d.,]+)\s*([KM])?/i.exec(clean(box.textContent));
          if (m) return String(Math.round(parseFloat(m[1].replace(/,/g, '')) * ({ K: 1e3, M: 1e6 }[(m[2] || '').toUpperCase()] || 1)));
        }
      }
    }
    return '';
  }

  function fresh() {
    const out = [], host = hostName();
    for (const article of document.querySelectorAll('[role="article"]')) {
      if (told.has(article)) continue;
      const c = comment(article);
      if (c) out.push({ node: article, id: c.id, name: c.name.slice(0, 60), text: c.text.slice(0, 1000), host: !!host && c.name === host });
    }
    return out;
  }

  async function tick() {
    if (busy) return;
    busy = true;
    try {
      if (!(await wanted())) {
        if (wasLive) { wasLive = false; await ask('fb-feed', { over: 1 }); }
        return;
      }
      wasLive = true;
      const lines = fresh();
      do {                                     // in batches small enough for one request
        const batch = [];
        while (lines.length && (!batch.length || encodeURIComponent(JSON.stringify(batch.concat(lines[0]).map(({ node, ...l }) => l))).length < 6000)) {
          batch.push(lines.shift());
        }
        const answer = await ask('fb-feed', { viewers: viewers(), lines: JSON.stringify(batch.map(({ node, ...l }) => l)) });
        if (!answer || !answer.reached || !answer.data || !answer.data.mine) break;   // tried again next time
        batch.forEach((l) => told.add(l.node));
      } while (lines.length);
    } finally {
      busy = false;
    }
  }

  async function say(text) {
    const boxes = [...document.querySelectorAll('[role="textbox"][contenteditable="true"]')];
    const box = boxes.find((b) => /comment/i.test(b.getAttribute('aria-label') || '')) || boxes.pop();
    if (!(await wanted()) || !box) return { ok: false, why: 'no Facebook live is running in Live Producer' };
    box.focus();
    document.execCommand('selectAll', false);
    document.execCommand('insertText', false, text);
    await sleep(250);
    const post = document.querySelector('[aria-label="Post comment"]');
    if (post && post.getAttribute('aria-disabled') !== 'true') post.click();
    else box.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true }));
    for (let i = 0; i < 25; i++) {
      await sleep(200);
      if (!box.isConnected || clean(box.textContent) === '') return { ok: true };
    }
    return { ok: false, why: 'Facebook did not post it' };
  }

  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (message.type !== 'fb-say') return;
    say(String(message.text || '')).then(respond, () => respond({ ok: false, why: 'it failed' }));
    return true;   // the answer comes later
  });
  setInterval(tick, 1000);
})();
