// What one row of TikTok's LIVE chat is, and one alert per gift streak (no page access here). tiktok.js reads the page.
globalThis.CrossChatTikTokRows = (() => {
  const { clean } = globalThis.CrossChatCommon;

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

  return { classify, giftStreaks, GIFT_QUIET, GIFT_AGAIN };
})();
