// On Facebook's Live Producer (where a Facebook live is started and ended; CrossChat opens it when OBS goes live), this
// script, while a live is running and CrossChat says Facebook is on:
//   - passes new comments and the viewer count to the CrossChat hub on this PC, which shows them in the CrossChat
//     window;
//   - types a reply that comes from that window into Live Producer's comment box and posts it;
//   - deletes a comment the streamer chose to delete in that window, through Live Producer's own comment menu.
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

  // The link with the commenter's name. Facebook marks each comment as an article whose links carry the comment's own
  // id; a viewer's comment starts with their picture, a link too (hidden from screen readers, no text), so the first
  // link with text is the name.
  const nameLink = (article) => [...article.querySelectorAll('a[href*="comment_id="]')].find((a) => clean(a.textContent)) || null;

  // One comment: its id (from the name link), the commenter's name and the words.
  function comment(article) {
    const link = nameLink(article);
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

  // Waits up to ms for find() to give something.
  async function until(find, ms) {
    for (let waited = 0; waited <= ms; waited += 100) {
      const found = find();
      if (found) return found;
      await sleep(100);
    }
    return null;
  }
  const named = (root, selector, pattern) => [...root.querySelectorAll(selector)].find((b) => pattern.test(clean(b.getAttribute('aria-label') || b.textContent)));

  // Deletes one comment the way the streamer would: its "..." menu, Delete, then Delete again in Facebook's question.
  // The comment is found by the id CrossChat got from it (the hub's "fb-" + its comment_id); nothing else is touched.
  async function remove(messageId) {
    if (!(await wanted())) return { ok: false, why: 'no Facebook live is running in Live Producer' };
    const article = [...document.querySelectorAll('[role="article"]')].find((a) => {
      const c = comment(a);
      return c && 'fb-' + c.id.replace(/[^\w=-]/g, '').slice(0, 120) === messageId;
    });
    if (!article) return { ok: false, why: 'that comment is no longer in Live Producer' };
    const menu = named(article, '[role="button"], button', /report this/i);     // "Edit, delete or report this"
    if (!menu) return { ok: false, why: 'Facebook shows no menu for that comment' };
    menu.click();
    const del = await until(() => {
      for (const list of document.querySelectorAll('[role="menu"]')) {
        const item = named(list, '[role="menuitem"], [role="button"]', /^Delete( comment)?$/i);
        if (item) return item;
      }
      return null;
    }, 3000);
    if (!del) {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true }));
      return { ok: false, why: "Facebook didn't offer Delete for that comment" };
    }
    del.click();
    const confirm = await until(() => {
      for (const box of document.querySelectorAll('[role="dialog"]')) {
        if (!/Delete Comment\?/i.test(clean(box.textContent))) continue;
        const yes = named(box, '[role="button"], button', /^Delete$/i);
        if (yes) return yes;
      }
      return null;
    }, 3000);
    if (!confirm) return { ok: false, why: "Facebook didn't ask to confirm the delete" };
    confirm.click();
    return (await until(() => !article.isConnected || !comment(article), 5000)) ? { ok: true } : { ok: false, why: 'Facebook did not delete it' };
  }

  if (typeof module === 'object' && module.exports) {      // Node (the tests): the parts above, nothing else
    module.exports = { nameLink };
    return;
  }

  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (message.type === 'fb-say') say(String(message.text || '')).then(respond, () => respond({ ok: false, why: 'it failed' }));
    else if (message.type === 'fb-mod' && message.action === 'delete') remove(String(message.message_id || '')).then(respond, () => respond({ ok: false, why: 'it failed' }));
    else if (message.type === 'fb-mod') respond({ ok: false, why: 'Facebook comments can only be deleted from CrossChat' });
    else return;
    return true;   // the answer comes later
  });
  setInterval(tick, 1000);
})();
