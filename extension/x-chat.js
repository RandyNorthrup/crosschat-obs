// While a livestream is running on this page (X's Live Studio), this script:
//   - passes its viewer count and new chat lines to the CrossChat hub on this PC, which shows them in the
//     CrossChat window;
//   - types a reply that comes from that window into the chat box here and sends it;
//   - ends the livestream when the hub says OBS has stopped streaming.
// It does nothing on any other page, and nothing when no livestream is running.
(() => {
  const { sleep, clean, ask, hash, waitFor } = globalThis.CrossChatCommon;
  const text = (el) => clean(el.innerText || el.textContent);
  const endButton = () => document.querySelector('button[aria-label="End livestream"]');
  const live = () => /^\/live\/\w/.test(location.pathname) && !!endButton();       // that button exists only while live
  const told = new WeakSet();                 // chat lines already passed on
  let wasLive = false, busy = false, ending = false;

  // The number X shows next to "Concurrent viewers" (it writes big ones as 1.2K), or '' when it shows none.
  function viewers() {
    const plain = (el) => (el.textContent || '').replace(/\s+/g, ' ').trim();
    const count = (s) => {
      const m = /^([\d,.]+) ?([KM])?$/.exec(s);
      const n = m ? parseFloat(m[1].replace(/,/g, '')) * ({ K: 1e3, M: 1e6 }[m[2]] || 1) : NaN;
      return isFinite(n) ? String(Math.round(n)) : '';
    };
    for (const el of document.querySelectorAll('span, h3, p')) {
      const label = /^Concurrent viewers ?(.*)$/.exec(plain(el));
      if (!label) continue;
      const n = count(label[1]) || (el.nextElementSibling ? count(plain(el.nextElementSibling)) : '');
      if (n) return n;
    }
    return '';
  }

  // Chat lines not passed on yet. X gives them no ids, so one is made from who said what and which time
  // they said it; the hub uses it to skip lines it already has (after a reload of this page, say).
  function fresh() {
    const region = document.querySelector('[role="region"][aria-label="Live chat messages"]');
    const out = [], times = {};
    for (const p of region ? region.querySelectorAll('p') : []) {
      const who = p.parentElement && p.parentElement.querySelector('a[href^="https://x.com/"]');
      if (!who || !text(p)) continue;
      const handle = who.getAttribute('href').split('/').pop(), key = handle + '\n' + text(p);
      times[key] = (times[key] || 0) + 1;
      if (!told.has(p)) out.push({ p, name: text(who), handle, text: text(p), id: hash(key) + 'n' + times[key] });
    }
    return out;
  }

  async function tick() {
    if (busy) return;
    busy = true;
    try {
      if (!live()) {
        if (wasLive) { wasLive = false; await ask('feed', { over: 1 }); }
        return;
      }
      wasLive = true;
      const now = { viewers: viewers() };
      const lines = fresh();
      let answer = lines.length ? null : await ask('feed', now);
      for (const line of lines) {
        answer = await ask('feed', { ...now, name: line.name, handle: line.handle, text: line.text, id: line.id });
        if (!answer || !answer.reached) break;      // the hub is not running: these lines are tried again
        told.add(line.p);
      }
      if (answer && answer.reached && answer.data.end && !ending) end();
    } finally {
      busy = false;
    }
  }

  async function end() {
    ending = true;
    endButton().click();
    const yes = await waitFor(() => {               // X asks "are you sure?": press the End button in that box
      if (!live()) return true;
      const box = [...document.querySelectorAll('[role="dialog"], [role="alertdialog"]')].pop();
      return box && [...box.querySelectorAll('button')].find((b) => /^end\b/i.test(text(b)));
    }, 10000);
    if (yes && yes !== true) yes.click();
    await waitFor(() => !live(), 20000);
    await ask('result', { ok: live() ? 0 : 1, mode: 'end', step: 'the End livestream button' });
    ending = false;
  }

  async function say(line) {
    const box = document.querySelector('input[aria-label="Message"]');
    const send = () => document.querySelector('button[aria-label="Send message"]');
    if (!live() || !box) return { ok: false, why: 'no livestream is running on the X page' };
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(box, line);
    box.dispatchEvent(new Event('input', { bubbles: true }));
    await sleep(200);
    if (!send() || send().disabled) return { ok: false, why: 'X would not take the message' };
    send().click();
    return (await waitFor(() => !box.isConnected || box.value === '', 5000, 200)) ? { ok: true } : { ok: false, why: 'X did not send it' };
  }

  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (message.type !== 'x-say') return;
    say(String(message.text || '')).then(respond);
    return true;   // the answer comes later
  });
  setInterval(tick, 2000);
})();
