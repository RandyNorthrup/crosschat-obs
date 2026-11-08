// What the page scripts share. manifest.json lists this file before them, and the scripts of one entry run in order in
// one global scope of their own (never the page's), so each just takes what it needs from CrossChatCommon.
globalThis.CrossChatCommon = (() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim();

  // One question to the extension's background part. null when it can't answer (the extension was updated under this page, say).
  const ask = (type, data) => new Promise((r) => {
    try { chrome.runtime.sendMessage({ type, data }, (a) => r(chrome.runtime.lastError ? null : a)); } catch (e) { r(null); }
  });

  function hash(s) {
    let h = 5381;
    for (let i = 0; i < s.length; i++) h = ((h * 33) ^ s.charCodeAt(i)) >>> 0;
    return h.toString(36);
  }

  // Waits by the clock, not by a count of short sleeps: a background tab runs its timers late. Gives what find() gave
  // last, having looked once more after the time was up.
  async function waitFor(find, ms, every = 250) {
    const end = Date.now() + ms;
    for (;;) {
      const found = find();
      if (found || Date.now() >= end) return found;
      await sleep(every);
    }
  }

  const BATCH_MOST = 50;                       // lines the hub reads from one request (hub.py: lines[:50])
  const BATCH_SIZE = 6000;                     // characters of them that fit in one request's address
  const forHub = (lines) => lines.map(({ node, sig, ...line }) => line);
  const size = (lines) => encodeURIComponent(JSON.stringify(forHub(lines))).length;

  // Passes new lines to the hub in batches small enough for one request; took(line) for each it has, and whatever it
  // doesn't have is tried again next time. Something always goes out (with no lines, `fields` still has the viewer count).
  async function sendLines(type, fields, lines, took) {
    do {
      const batch = [];
      while (lines.length && batch.length < BATCH_MOST && (!batch.length || size(batch.concat(lines[0])) < BATCH_SIZE)) batch.push(lines.shift());
      const answer = await ask(type, { ...fields, lines: JSON.stringify(forHub(batch)) });
      if (!answer || !answer.reached || !answer.data || !answer.data.mine) return;
      batch.forEach(took);
    } while (lines.length);
  }

  return { sleep, clean, ask, hash, waitFor, sendLines, BATCH_MOST };
})();
