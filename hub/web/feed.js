// What the chat window and the on-stream widgets both do to a message before it shows: third-party emotes (7TV,
// BetterTTV, FrankerFaceZ) and the chat widget's delay. No page needed: tests/js/feed.test.mjs loads it in node.
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.CrossChatFeed = api;
})(typeof self !== 'undefined' ? self : globalThis, function () {
  const LONGEST_CODE = 100;

  // The hub's {CODE: url} list as a Map, keeping one-word codes with https pictures only.
  function emoteMap(raw) {
    const out = new Map();
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return out;
    Object.keys(raw).forEach((code) => {
      const url = raw[code];
      if (!code || code.length > LONGEST_CODE || /\s/.test(code)) return;
      if (typeof url === 'string' && /^https:\/\/[^\s"'<>()\\]+$/.test(url)) out.set(code, url);
    });
    return out;
  }

  // Message pieces ([{ text } | { emote, alt }], Twitch's own emotes already cut out) with every whole word found in
  // `map` turned into { url, alt }. Words are split on spaces and must match exactly: "KEKW" is not "kekw".
  function withEmotes(pieces, map) {
    if (!map || !map.size) return pieces;
    const out = [];
    const text = (t) => { const last = out[out.length - 1]; if (last && last.text !== undefined) last.text += t; else out.push({ text: t }); };
    pieces.forEach((piece) => {
      if (piece.text === undefined) { out.push(piece); return; }
      piece.text.split(/(\s+)/).forEach((word) => {
        if (!word) return;
        const url = map.get(word);
        if (url) out.push({ url, alt: word }); else text(word);
      });
    });
    return out;
  }

  // Does a delete, purge or hide event take message m away? delete: { id }. purge and hide: { p, name } for everything
  // one viewer wrote (hide may also carry an id, or leave out p for every platform).
  function takes(e, m) {
    if (!e || !m) return false;
    if (e.id) return m.id === e.id;
    if (e.type !== 'purge' && e.type !== 'hide') return false;
    const who = String(e.name || '').toLowerCase();
    if (!who) return false;
    return (!e.p || m.p === e.p) && (String(m.name || '').toLowerCase() === who || String(m.handle || '').toLowerCase() === who);
  }

  // Messages held back before they show, so one deleted or hidden in the meantime never reaches the stream. The page
  // runs the clock: add(m, until), then due(now) hands back what may show, oldest first.
  function holdQueue() {
    let held = [];
    return {
      add(m, until) { held.push({ m, until }); },
      drop(test) { const before = held.length; held = held.filter((h) => !test(h.m)); return before - held.length; },
      due(now) { const out = held.filter((h) => h.until <= now); held = held.filter((h) => h.until > now); return out.map((h) => h.m); },
      next() { return held.reduce((soonest, h) => Math.min(soonest, h.until), Infinity); },
      clear() { held = []; },
      get size() { return held.length; },
    };
  }

  return { emoteMap, withEmotes, takes, holdQueue };
});
