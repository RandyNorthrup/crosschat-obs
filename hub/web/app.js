// The CrossChat app: the chat window on the streaming PC (http://127.0.0.1:4466/) and the companion on a phone, tablet
// or another PC on the home network (http://<this PC>:4467/). One page for both; GET /whoami says which it is.
//
// Everything is sent through the hub (POST /send, /mod, ...). The hub does Twitch itself once Twitch is connected; YouTube
// and X go out through the CrossChat extension, which only the chat window on the streaming PC has. That window is the
// hub's "executor": it receives `outbox` jobs, hands them to the extension and reports back with POST /outbox/result.

// ---- the pure part (no page needed; tests/js/app.test.mjs loads it in node) -----------------------------------------
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.CrossChatApp = api;
})(typeof self !== 'undefined' ? self : globalThis, function () {
  const NAMES = { twitch: ['Twitch', 'TW'], youtube: ['YouTube', 'YT'], kick: ['Kick', 'K'], x: ['X', 'X'], tiktok: ['TikTok', 'TT'],
                  facebook: ['Facebook', 'FB'], instagram: ['Instagram', 'IG'], rumble: ['Rumble', 'RM'] };
  // Platforms a reply can go to, and the longest message each takes. Kick only once Kick is connected in Settings.
  const LIMIT = { twitch: 500, youtube: 200, x: 140, kick: 500, tiktok: 150, facebook: 8000, instagram: 2200, rumble: 200 };
  // Chats read and answered through the streamer's own live page in the browser (the extension does the typing).
  const PAGE_PLATFORMS = ['tiktok', 'facebook', 'instagram', 'rumble'];
  const QUICK_MAX = 30, QUICK_LENGTH = 100;
  const LONGEST_TIMEOUT = { twitch: 1209600, kick: 604800 };    // 14 days; 7 days

  const name = (p) => (NAMES[p] ? NAMES[p][0] : p);
  const takesReplies = (p, kick) => !!LIMIT[p] && (p !== 'kick' || kick === 'on');
  // Chats that can take a reply now. kick: the state of the Kick connection ("on" once connected).
  const openPlatforms = (states, kick) => Object.keys(LIMIT).filter((p) => (states || {})[p] === 'on' && takesReplies(p, kick));
  const targetsFor = (states, replyTo, kick) => (replyTo ? [replyTo.p] : openPlatforms(states, kick));
  const tooLong = (text, to) => to.filter((p) => LIMIT[p] && [...text].length > LIMIT[p]);
  const clean = (text) => String(text || '').replace(/\s+/g, ' ').trim();

  // What can carry a message to platform p right now: { ok, why }.
  function route(p, ctx) {
    if (!LIMIT[p]) return { ok: false, why: name(p) + ' chat can only be read from CrossChat' };
    // Twitch and Kick replies go through the platform's own API, so only once connected in Settings.
    if (p === 'twitch' || p === 'kick') {
      return ctx[p] === 'on' ? { ok: true } : { ok: false, why: 'Connect ' + name(p) + ' in Settings' + (ctx.remote ? ' on the streaming PC' : '') + ' to reply on ' + name(p) };
    }
    if (ctx.executor) return { ok: true };
    return { ok: false, why: ctx.remote ? 'Needs the CrossChat window open on the streaming PC' : 'Needs this window open in Chrome or Edge with the CrossChat extension' };
  }

  // Can message m be answered on its own platform: { ok, why }.
  function canReply(m, ctx) {
    if (!m || m.kind !== 'chat' || !m.name) return { ok: false, why: 'Only chat messages can be answered' };
    if (!LIMIT[m.p]) return { ok: false, why: name(m.p) + ' chat can only be read from CrossChat' };
    if ((ctx.states || {})[m.p] !== 'on') return { ok: false, why: name(m.p) + ' chat is not open right now' };
    return route(m.p, ctx);
  }

  // The moderation entries for message m: [{ action, seconds, label, ok, why, danger, custom }].
  function modMenu(m, ctx) {
    const off = (why) => [{ action: 'delete', label: 'Delete message', ok: false, why }];
    if (!m || m.kind !== 'chat' || !m.name) return off('Only chat messages can be moderated');
    if ((m.badges || []).some((b) => b === 'broadcaster' || b === 'owner')) return off("That's you");
    if (m.p === 'x') return off("X chat can't be moderated from CrossChat");
    if (m.p === 'facebook' || m.p === 'rumble') {   // through the platform's own page, by the extension in this window
      const why = ctx.executor ? '' : ctx.remote ? 'Needs the CrossChat window open on the streaming PC' : 'Needs this window open in Chrome or Edge with the CrossChat extension';
      const ok = !why && !!m.mid;
      const whyNot = why || (m.mid ? '' : name(m.p) + ' gave this message no id');
      if (m.p === 'facebook') return [{ action: 'delete', label: 'Delete comment', ok, why: whyNot }];
      return [
        { action: 'delete', label: 'Delete message', ok, why: whyNot },
        { action: 'timeout', seconds: 300, label: 'Mute 5 minutes', ok, why: whyNot },
        { action: 'mute', label: 'Mute for this stream', ok, why: whyNot },
        { action: 'ban', label: 'Mute forever', danger: true, ok, why: whyNot },
      ];
    }
    if (PAGE_PLATFORMS.includes(m.p)) return off('Moderate ' + name(m.p) + ' chat in ' + name(m.p));
    if (m.p === 'twitch' || m.p === 'kick') {     // both through the platform's own API, once connected in Settings
      const why = ctx[m.p] === 'on' ? '' : 'Connect ' + name(m.p) + (ctx.remote ? ' on the streaming PC (Settings)' : ' in Settings') + ' to moderate';
      const ok = !why;
      return [
        { action: 'delete', label: 'Delete message', ok: ok && !!m.mid, why: why || (m.mid ? '' : name(m.p) + ' gave this message no id') },
        { action: 'timeout', seconds: 600, label: 'Timeout 10 minutes', ok, why },
        { action: 'timeout', seconds: 3600, label: 'Timeout 1 hour', ok, why },
        { action: 'timeout', label: 'Timeout for…', custom: true, ok, why },
        { action: 'ban', label: 'Ban', danger: true, ok, why },
        { action: 'unban', label: 'Unban', ok, why },
      ];
    }
    if (m.p === 'youtube') {
      const why = ctx.executor ? '' : ctx.remote ? 'Needs the CrossChat window open on the streaming PC' : 'Needs this window open in Chrome or Edge with the CrossChat extension';
      const ok = !why;
      return [
        { action: 'delete', label: 'Remove message', ok, why },
        { action: 'timeout', seconds: 300, label: 'Timeout 5 minutes', ok, why },
        { action: 'ban', label: 'Hide user on this channel', danger: true, ok, why },
      ];
    }
    return off(name(m.p) + " chat can't be moderated from CrossChat");
  }

  function duration(seconds) {
    const s = Number(seconds) || 0;
    if (s < 3600) return Math.max(1, Math.round(s / 60)) + ' min';
    if (s < 86400) return Math.round(s / 360) / 10 + ' h';
    return Math.round(s / 8640) / 10 + ' days';
  }

  function describe(action, who, seconds) {
    return { delete: 'removed the message from ' + who, timeout: 'timed out ' + who + ' for ' + duration(seconds),
             mute: 'muted ' + who + ' for this stream', ban: 'banned ' + who, unban: 'unbanned ' + who }[action] || action + ' ' + who;
  }

  // The quick-reply list as the hub accepts it: trimmed, no blanks or repeats, at most 30 of at most 100 characters.
  function cleanQuick(list) {
    const out = [];
    (Array.isArray(list) ? list : []).forEach((t) => {
      const s = [...clean(t)].slice(0, QUICK_LENGTH).join('');
      if (s && !out.includes(s) && out.length < QUICK_MAX) out.push(s);
    });
    return out;
  }

  function inView(view, m, starred) {
    if (view === 'questions') return !!(m && m.question);
    if (view === 'starred') return !!(m && starred && starred.has(m.id));
    return true;
  }

  // "@name " for a reply to message m (X uses the @handle).
  function mention(m) {
    const who = (m && (m.handle || m.name)) || '';
    return who ? (who.startsWith('@') ? '' : '@') + who + ' ' : '';
  }

  // Seconds until `expires` (Unix seconds or milliseconds).
  function secondsLeft(expires, now) {
    const at = Number(expires) || 0;
    return Math.max(0, Math.round(((at < 1e12 ? at * 1000 : at) - (now || Date.now())) / 1000));
  }

  // A viewer's own name colour, kept legible on this theme.
  function readable(color, light) {
    const m = /^#([0-9a-f]{6})$/i.exec(color || '');
    if (!m) return '';
    let [r, g, b] = [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16));
    const lum = 0.299 * r + 0.587 * g + 0.114 * b;
    if (!light && lum < 110) { const k = (110 - lum) / 255; [r, g, b] = [r, g, b].map((v) => Math.round(v + (255 - v) * (k + 0.25))); }
    if (light && lum > 140) { const k = (lum - 140) / 255 + 0.25; [r, g, b] = [r, g, b].map((v) => Math.round(v * (1 - k))); }
    return 'rgb(' + r + ',' + g + ',' + b + ')';
  }

  // The message text in pieces, Twitch emotes ("id:a-b,c-d/id2:e-f") cut out by code point: [{ text } | { emote, alt }].
  function pieces(text, emotes) {
    const chars = [...String(text || '')], ranges = [];
    String(emotes || '').split('/').filter(Boolean).forEach((e) => {
      const [id, spots] = e.split(':');
      (spots || '').split(',').forEach((s) => { const [a, z] = s.split('-').map(Number); ranges.push([a, z, id]); });
    });
    const out = [];
    let at = 0;
    ranges.sort((a, b) => a[0] - b[0]).forEach(([a, z, id]) => {
      if (!/^\w+$/.test(id || '') || !(a >= at && z >= a && z < chars.length)) return;
      if (a > at) out.push({ text: chars.slice(at, a).join('') });
      out.push({ emote: id, alt: chars.slice(a, z + 1).join('') });
      at = z + 1;
    });
    if (at < chars.length) out.push({ text: chars.slice(at).join('') });
    return out;
  }

  // A custom timeout typed in minutes, as the seconds platform p takes: Twitch 1 minute to 14 days, Kick whole minutes
  // (rounded up) from 1 minute to 7 days.
  function timeoutSeconds(p, minutes) {
    const most = LONGEST_TIMEOUT[p] || LONGEST_TIMEOUT.twitch, n = Number(minutes) || 0;
    if (p === 'kick') return Math.min(most / 60, Math.max(1, Math.ceil(n))) * 60;
    return Math.min(most, Math.max(60, Math.round(n * 60)));
  }

  // ---- reading chat aloud ----------------------------------------------------------------------------------------------
  const TTS_READ = ['all', 'questions', 'events', 'command', 'featured'];
  const TTS_PLATFORMS = ['twitch', 'youtube', 'kick', 'x', 'tiktok', 'facebook', 'instagram', 'rumble'];

  // Text-to-speech settings as the hub keeps them, from whatever came in (missing or wrong values get the defaults).
  function ttsSettings(raw) {
    const s = raw && typeof raw === 'object' ? raw : {};
    const num = (v, lo, hi, d) => { const n = v === null || v === '' ? NaN : Number(v); return isFinite(n) ? Math.min(hi, Math.max(lo, n)) : d; };
    const list = Array.isArray(s.platforms) ? TTS_PLATFORMS.filter((p) => s.platforms.includes(p)) : 'all';
    return {
      enabled: s.enabled === true,
      read: TTS_READ.includes(s.read) ? s.read : 'all',
      command: [...clean(s.command)].slice(0, 20).join('') || '!tts',
      names: s.names !== false,
      max_chars: Math.round(num(s.max_chars, 20, 500, 200)),
      skip_links: s.skip_links !== false,
      platforms: list === 'all' || list.length === TTS_PLATFORMS.length ? 'all' : list,
      voice: typeof s.voice === 'string' ? s.voice.slice(0, 200) : '',
      rate: Math.round(num(s.rate, 0.5, 2, 1) * 10) / 10,
      volume: Math.round(num(s.volume, 0, 1, 1) * 100) / 100,
    };
  }

  // Voices that are not on this PC (Edge's "Online (Natural)" ones, Chrome's Google ones) send the text they read to
  // Microsoft or Google. They are listed apart and never picked unless the streamer picks one by name.
  const onlineVoice = (v) => !!v && v.localService === false;
  const voiceMaker = (v) => (/google/i.test((v && v.name) || '') ? 'Google' : 'Microsoft');
  function voiceGroups(voices, lang) {
    const base = String(lang || 'en').slice(0, 2).toLowerCase();
    const mine = (v) => String(v.lang || '').toLowerCase().startsWith(base);
    const all = (voices || []).filter((v) => v && v.name);
    const ordered = all.filter(mine).concat(all.filter((v) => !mine(v)));
    return { local: ordered.filter((v) => !onlineVoice(v)), online: ordered.filter(onlineVoice) };
  }
  // The voice to read with: exactly the saved one, else the first voice on this PC (null when there is none).
  function pickVoice(voices, saved, lang) {
    const exact = saved && (voices || []).find((v) => v && v.name === saved);
    return exact || voiceGroups(voices, lang).local[0] || null;
  }

  // The read-aloud queue on the speaker: one at a time, in order. add() and done() hand back what to say now, if anything;
  // done() for an item that is no longer the current one (it was stopped) changes nothing.
  function speech(longest) {
    let queue = [], current = null;
    const next = () => { current = queue.shift() || null; return current; };
    return {
      get current() { return current; },
      get waiting() { return queue.length; },
      add(item) {
        if (!item || !clean(item.text)) return null;
        if (item.id && ((current && current.id === item.id) || queue.some((q) => q.id === item.id))) return null;
        queue.push(item);
        if (queue.length > (longest || 30)) queue.shift();
        return current ? null : next();
      },
      done(item) { return item && item === current ? next() : null; },
      stop() { const had = !!current || queue.length > 0; queue = []; current = null; return had; },
    };
  }

  // ---- filters, connection health, chat logs -----------------------------------------------------------------------------
  const LIST_MAX = 200, LIST_LENGTH = 50;
  // A filter list as the hub keeps it: trimmed, no blanks or repeats (in any case), at most 200 of at most 50 characters.
  function cleanList(list) {
    const out = [], seen = new Set();
    (Array.isArray(list) ? list : []).forEach((t) => {
      const s = [...clean(t)].slice(0, LIST_LENGTH).join('');
      if (s && !seen.has(s.toLowerCase()) && out.length < LIST_MAX) { seen.add(s.toLowerCase()); out.push(s); }
    });
    return out;
  }
  const filterSettings = (raw) => {
    const s = raw && typeof raw === 'object' ? raw : {};
    return { words: cleanList(s.words), users: cleanList(s.users), hide_commands: s.hide_commands === true, bots: s.bots === true, joins: s.joins === true };
  };

  // "45 s", "12 m", "1 h 12 m", "2 d 3 h".
  function span(ms) {
    const s = Math.max(0, Math.round((Number(ms) || 0) / 1000));
    if (s < 60) return s + ' s';
    const m = Math.floor(s / 60);
    if (m < 60) return m + ' m';
    const h = Math.floor(m / 60);
    if (h < 24) return h + ' h' + (m % 60 ? ' ' + (m % 60) + ' m' : '');
    return Math.floor(h / 24) + ' d' + (h % 24 ? ' ' + (h % 24) + ' h' : '');
  }
  const ms = (t) => { const n = Number(t) || 0; return n && n < 1e12 ? n * 1000 : n; };

  // One platform's connection health: "connected 1 h 12 m · last message 8 s ago · 2 reconnects".
  function health(h, now) {
    if (!h) return '';
    now = now || Date.now();
    const since = ms(h.since), last = ms(h.last), n = Number(h.reconnects) || 0;
    const out = [since ? 'connected ' + span(now - since) : 'not connected'];
    if (since || last) out.push(last ? 'last message ' + span(now - last) + ' ago' : 'no messages yet');
    if (n) out.push(n + (n === 1 ? ' reconnect' : ' reconnects'));
    return out.join(' · ');
  }

  const validLog = (name) => typeof name === 'string' && /^[\w-]{1,60}$/.test(name);
  function bytes(n) {
    n = Number(n) || 0;
    if (n < 1024) return n + ' B';
    if (n < 1048576) return Math.round(n / 1024) + ' KB';
    return (n / 1048576).toFixed(1) + ' MB';
  }
  // The messages of a saved chat that match: every searched word in the name or text, one platform, questions only.
  function logFilter(messages, f) {
    f = f || {};
    const words = clean(f.text).toLowerCase().split(' ').filter(Boolean);
    return (Array.isArray(messages) ? messages : []).filter((m) => m && (!f.p || f.p === 'all' || m.p === f.p) && (!f.questions || m.question)
      && words.every((w) => [m.name, m.handle, m.system, m.text].join(' ').toLowerCase().includes(w)));
  }

  // ---- Settings → Channels & options: the parts of config.json the hub lets this window change -----------------------
  // Each field: where it lives in config.json, how it is shown, and one line on what it does. The hub checks every value
  // again (POST /config) and says which changes need OBS restarted.
  const CONFIG_FIELDS = [
    { key: 'twitch', group: 'Channels', label: 'Twitch channel', type: 'text', max: 200, placeholder: 'twitch.tv/yourname', hint: 'Your channel name or link. CrossChat reads its chat.' },
    { key: 'youtube', group: 'Channels', label: 'YouTube channel', type: 'text', max: 200, placeholder: '@yourhandle', hint: 'Your @handle or channel link. Chat shows up once you are live.' },
    { key: 'kick', group: 'Channels', label: 'Kick channel', type: 'text', max: 200, placeholder: 'kick.com/yourname', hint: 'Your channel name or link. CrossChat reads its chat.' },
    { key: 'tiktok', group: 'Channels', label: 'TikTok @name', type: 'text', max: 200, placeholder: '@yourname', hint: 'Your TikTok LIVE page opens in your browser when you go live, and its chat is read there.' },
    { key: 'facebook', group: 'Channels', label: 'Facebook Live', type: 'bool', hint: 'Reads comments from Live Producer, which opens in your browser when you go live.' },
    { key: 'instagram', group: 'Channels', label: 'Instagram Live', type: 'bool', hint: 'Reads comments from Instagram’s live producer (Create → Live video on instagram.com), which opens in your browser when you go live.' },
    { key: 'x.enabled', group: 'X', label: 'X livestreams', type: 'bool', hint: 'Reads and answers the chat of your livestream on X.' },
    { key: 'x.auto_go_live', group: 'X', label: 'Go live on X by itself', type: 'bool', hint: 'Starts the X livestream a few seconds after OBS starts streaming.' },
    { key: 'x.title', group: 'X', label: 'Livestream title', type: 'text', max: 120, placeholder: 'Live now', hint: 'The title X shows, unless a title file is set.' },
    { key: 'x.title_file', group: 'X', label: 'Title file', type: 'text', max: 260, placeholder: 'C:\\stream\\title.txt', hint: 'A text file whose first line becomes the title. Leave empty to use the title above.' },
    { key: 'x.source', group: 'X', label: 'Source name on X', type: 'text', max: 40, placeholder: 'OBS', hint: 'The video source X Live Studio should pick: the name it shows for OBS.' },
    { key: 'open_window_on_stream_start', group: 'Window', label: 'Open this window when the stream starts', type: 'bool', hint: 'Chat is in front of you the moment OBS goes live.' },
    { key: 'close_window_seconds_after_stream', group: 'Window', label: 'Close the windows after the stream (seconds)', type: 'int', min: 0, max: 3600, hint: 'How long the chat window and live pages stay open once OBS stops streaming.' },
    { key: 'window', group: 'Window', label: 'Window position', type: 'select', options: [['auto', 'Right edge of the main screen'], ['custom', 'Where config.json says']], hint: 'Where this window opens. Keep it somewhere OBS doesn’t capture.' },
    { key: 'emotes.7tv', group: 'Emotes', label: '7TV emotes', type: 'bool', hint: 'Shows 7TV emote pictures here and on stream.' },
    { key: 'emotes.bttv', group: 'Emotes', label: 'BetterTTV emotes', type: 'bool', hint: 'Shows BetterTTV emote pictures here and on stream.' },
    { key: 'emotes.ffz', group: 'Emotes', label: 'FrankerFaceZ emotes', type: 'bool', hint: 'Shows FrankerFaceZ emote pictures here and on stream.' },
    { key: 'logs.enabled', group: 'Chat history', label: 'Save chat history', type: 'bool', hint: 'Keeps every stream’s chat on this PC to search and export. Applies from the next stream.' },
    { key: 'logs.keep_days', group: 'Chat history', label: 'Keep chat history for (days)', type: 'int', min: 1, max: 3650, hint: 'Streams older than this are deleted from this PC.' },
    { key: 'remote.enabled', group: 'Companion', label: 'Companion for phones and tablets', type: 'bool', hint: 'Lets devices you pair on your home network read and answer chat.' },
    { key: 'remote.port', group: 'Companion', label: 'Companion port', type: 'int', min: 1024, max: 65535, hint: 'Change it only if another program uses it. Paired devices then need the new address.' },
  ];
  const CONFIG_KEYS = CONFIG_FIELDS.map((f) => f.key);

  // A field as the hub takes it, from what was typed or ticked: { value } or { why } in plain words.
  function configValue(field, raw) {
    if (field.type === 'bool') return { value: raw === true };
    if (field.type === 'int') {
      const text = String(raw == null ? '' : raw).trim();
      const n = /^\d+$/.test(text) ? Number(text) : NaN;
      if (!(n >= field.min && n <= field.max)) return { why: field.label + ': a whole number from ' + field.min + ' to ' + field.max + '.' };
      return { value: n };
    }
    const text = clean(raw);
    if ([...text].length > (field.max || 200)) return { why: field.label + ': at most ' + field.max + ' characters.' };
    if (field.type === 'select' && !field.options.some(([v]) => v === text)) return { why: field.label + ': pick one of the choices.' };
    return { value: text };
  }

  // The fields that differ from what the hub has, to send with POST /config ({} when nothing changed).
  function configChanges(saved, now) {
    const out = {};
    CONFIG_KEYS.forEach((k) => { if (now && k in now && now[k] !== (saved || {})[k]) out[k] = now[k]; });
    return out;
  }

  // ---- viewer cards --------------------------------------------------------------------------------------------------
  // Where a viewer's card comes from: GET /viewer for one platform and name (plus the platform's id when known), and
  // what to search for.
  function viewerPath(who, q) {
    const out = ['p=' + encodeURIComponent(who.p || ''), 'name=' + encodeURIComponent(String(who.name || '').slice(0, 100))];
    if (who.uid && /^[\w.:@|-]{1,128}$/.test(who.uid)) out.push('uid=' + encodeURIComponent(who.uid));
    const search = clean(q).slice(0, 100);
    if (search) out.push('q=' + encodeURIComponent(search));
    return '/viewer?' + out.join('&');
  }

  // The card's short facts, in plain words. at(t): a time of day for t.
  function viewerFacts(card, at) {
    if (!card || !card.ok) return [];
    const out = [], n = Number(card.count) || 0, past = Number(card.past_streams) || 0;
    if (card.first_ever) out.push('First message ever in your channel');
    if (card.first_seen) out.push('First message this stream at ' + at(card.first_seen));
    out.push(n ? n + (n === 1 ? ' message this stream' : ' messages this stream') : 'No messages this stream yet');
    if (past) out.push('Chatted in ' + past + (past === 1 ? ' earlier stream' : ' earlier streams') + (card.truncated ? ' (the most recent ones)' : ''));
    else if (!card.first_ever) out.push('Not in the chat history of earlier streams');
    return out;
  }

  // The latest chat message on a card, to moderate, read aloud or reply to.
  const viewerLatest = (card) => ((card && card.stream) || []).find((m) => m && m.kind === 'chat') || null;

  // The word on an event's tag in the chat window, by alert type (theme.js alertKind).
  const ALERT_WORDS = { sub: 'Sub', resub: 'Resub', gift: 'Gift', raid: 'Raid', cheer: 'Bits', member: 'Member', superchat: 'Super Chat',
                        sticker: 'Super Sticker', rant: 'Rant', follow: 'Follow', share: 'Share', like: 'Likes', join: 'Joined', other: 'Event' };
  const alertWord = (kind) => ALERT_WORDS[kind] || ALERT_WORDS.other;

  // ---- the update notice, Discord ------------------------------------------------------------------------------------
  // The only link the update notice may open: a CrossChat release page on GitHub ('' for anything else).
  // The link is rebuilt from CrossChat's own address and the version's numbers, so nothing from the message reaches the page.
  const RELEASES = 'https://github.com/RandyNorthrup/crosschat-obs/releases/tag/v';
  const releaseLink = (url) => {
    const m = /^https:\/\/github\.com\/RandyNorthrup\/crosschat-obs\/releases\/tag\/v(\d{1,4})\.(\d{1,4})\.(\d{1,4})$/.exec(typeof url === 'string' ? url : '');
    return m ? RELEASES + [m[1], m[2], m[3]].map(Number).join('.') : '';
  };
  // The extension in this browser is older than CrossChat: an unpacked extension keeps its old code after an update
  // until it is reloaded in chrome://extensions.
  const versionParts = (v) => (/^(\d{1,4})\.(\d{1,4})\.(\d{1,4})$/.exec(typeof v === 'string' ? v : '') || []).slice(1).map(Number);
  const extensionBehind = (ext, hub) => {
    const a = versionParts(ext), b = versionParts(hub);
    if (a.length !== 3 || b.length !== 3) return false;
    for (let i = 0; i < 3; i++) if (a[i] !== b[i]) return a[i] < b[i];
    return false;
  };
  // The streaming computer is a Mac (navigator.platform there): it has no Start menu, and the installer puts the
  // shortcuts in Applications → CrossChat in the home folder.
  const onMac = (platform) => /^Mac/.test(typeof platform === 'string' ? platform : '');
  const openChatHow = (platform) => (onMac(platform) ? 'Applications → CrossChat → Open chat (the Applications folder in your home folder)'
    : 'Start menu → CrossChat → Open chat');
  // A Discord webhook URL, the way Discord's "Copy Webhook URL" gives it (the hub checks it again, and with Discord).
  const discordWebhook = (url) => /^https:\/\/(discord\.com|discordapp\.com|ptb\.discord\.com|canary\.discord\.com)\/api\/webhooks\/\d{15,22}\/[\w-]{30,100}$/.test(clean(url));
  // How long to wait for a reply, moderation or a window job (ms). YouTube moderation may first have to open YouTube's
  // chat pop-out (the hub waits as long: YT_MOD_SECONDS); a window job may wait for a window that is still opening.
  const patience = (job) => (job && job.kind === 'mod' && job.p === 'youtube' ? 75000
    : 25000 + (job && job.kind === 'window' ? Math.min(Math.max(Number(job.wait) || 0, 0), 60) * 1000 : 0));

  return { NAMES, LIMIT, PAGE_PLATFORMS, QUICK_MAX, QUICK_LENGTH, LIST_MAX, LIST_LENGTH, TTS_READ, TTS_PLATFORMS, name, takesReplies, openPlatforms, targetsFor,
           tooLong, clean, route, canReply, modMenu, duration, describe, cleanQuick, inView, mention, secondsLeft, readable, pieces, timeoutSeconds,
           ttsSettings, onlineVoice, voiceMaker, voiceGroups, pickVoice, speech, cleanList, filterSettings, span, health, validLog, bytes, logFilter,
           CONFIG_FIELDS, CONFIG_KEYS, configValue, configChanges, viewerPath, viewerFacts, viewerLatest, alertWord, releaseLink, extensionBehind,
           discordWebhook, onMac, openChatHow, patience };
});

// ---- the page ---------------------------------------------------------------------------------------------------------
if (typeof document !== 'undefined' && document.getElementById('list')) (function (A) {
  const $ = (id) => document.getElementById(id);
  const Q = new URLSearchParams(location.search);
  const DEMO = Q.has('demo'), DEMO_KIND = Q.get('demo') || '';
  const DRY = Q.has('dry');                       // ?dry: a test, nothing is posted anywhere
  const list = $('list'), jump = $('jump'), say = $('say');
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue('--' + v).trim();
  const store = (key, value) => { try { if (value === undefined) return localStorage.getItem(key); localStorage.setItem(key, value); } catch (e) { return null; } return null; };
  const touch = matchMedia('(hover: none)');

  const F = globalThis.CrossChatFeed || { emoteMap: () => new Map(), withEmotes: (p) => p };
  const T = globalThis.CrossChatTheme;            // alert sentences, the same as on stream (theme.js)
  const ctx = { remote: false, device: null, version: '', lanUrl: null, executor: false, executorKnown: false, twitch: 'off',
                bridge: !!document.documentElement.dataset.crosschat, states: {}, unpaired: false };
  let counts = {}, starred = new Set(), quick = [], devices = [], twitchAuth = { state: 'off' }, kickAuth = { state: 'off' }, rumbleAuth = { state: 'off' }, pairTimer = null;
  let discordAuth = { state: 'off' }, companion = { tailscale: false }, update = { check: false };
  let tts = A.ttsSettings({}), filters = A.filterSettings({}), health = {}, emotes = new Map();
  let replyTo = null, featuredId = null, view = 'all', pinned = true, ding = store('ding') === '1', audio, sending = false, feed = null;
  const msgs = new Map();                         // id -> message, for the action sheet and featuring
  const waiting = {}, early = {}, echoes = [];    // jobs this page started; answers that came before their job id; lines sent to several platforms

  function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  const lightNow = () => document.documentElement.dataset.theme === 'light' ||
    (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: light)').matches);

  // The page fills the visible part of the screen, so the box stays above a phone's keyboard.
  if (window.visualViewport) {
    const fit = () => document.documentElement.style.setProperty('--app-h', Math.round(visualViewport.height) + 'px');
    visualViewport.addEventListener('resize', fit); fit();
  }

  // ---- talking to the hub -----------------------------------------------------------------------------------------
  async function api(path, body) {
    if (DEMO) return demoApi(path, body || {});
    try {
      const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}), cache: 'no-store' });
      if (r.status === 401 || r.status === 403) { if (ctx.remote) unpaired(); return { ok: false, why: 'this device is not paired' }; }
      return await r.json();
    } catch (e) {
      return { ok: false, why: 'CrossChat did not answer' };
    }
  }

  // Wait for the `sent` event of a job this page started.
  function track(id, job) {
    job.timer = setTimeout(() => finish(id, null), A.patience(job));
    waiting[id] = job;
    if (early[id]) { const a = early[id]; delete early[id]; finish(id, a); }
  }

  function finish(id, answer) {
    const job = waiting[id];
    if (!job) { early[id] = answer; const keys = Object.keys(early); if (keys.length > 50) delete early[keys[0]]; return; }
    delete waiting[id]; clearTimeout(job.timer);
    if (job.kind === 'mod') {
      const who = A.name(job.p);
      if (answer && answer.ok) note(who + ': ' + A.describe(job.action, job.who, job.seconds) + '.', 'good');
      else note(who + ': could not ' + ({ delete: 'remove that message', timeout: 'time out ' + job.who, mute: 'mute ' + job.who, ban: 'ban ' + job.who, unban: 'unban ' + job.who }[job.action] || job.action)
                + ' (' + ((answer && answer.why) || 'no answer') + ')', 'bad');
      return;
    }
    if (job.box) sending = false;
    if (!answer) note('Not sent: CrossChat got no answer in time.' + (ctx.remote ? ' Is the chat window open on the streaming PC?' : ''), 'bad');
    else {
      const failed = job.to.filter((p) => !(answer[p] && answer[p].ok));
      failed.forEach((p) => note(A.name(p) + ': not sent (' + ((answer[p] && answer[p].why) || 'no answer') + ')', 'bad'));
      if (job.box && failed.length < job.to.length) { say.value = ''; setReply(null); }
      if (DRY && !failed.length) note('Test mode: nothing was posted.', 'good');
    }
    drawPlatforms();
    if (job.box && !touch.matches) say.focus();
  }

  // ---- the executor: the chat window on the streaming PC hands jobs to the extension --------------------------------
  // Replies, moderation, and window jobs: the extension places and closes CrossChat's own windows for the hub.
  const jobs = {};
  let jobN = 0;
  function runJob(job) {
    const n = ++jobN;
    jobs[n] = { job, timer: setTimeout(() => done(n, null), A.patience(job)) };
    if (job.kind === 'mod') {
      window.postMessage({ crosschat: 'mod', n, p: job.p, action: job.action, message_id: job.message_id || '', user_id: job.user_id || '',
                           name: job.name || '', text: job.text || '', seconds: job.seconds || 0, reason: job.reason || '' }, location.origin);
    } else if (job.kind === 'window') {
      if (!document.documentElement.dataset.crosschatWindows) { done(n, { ok: false, why: 'the CrossChat extension here is too old for window jobs' }); return; }
      window.postMessage({ crosschat: 'window', n, action: job.action, role: job.role, url: job.url || '', box: job.box || null,
                           window: job.window || 0, known: job.known || [], wait: job.wait || 0 }, location.origin);
    } else {
      window.postMessage({ crosschat: 'send', n, to: job.to || [], text: job.text || '', reply: job.reply || null, dry: !!job.dry }, location.origin);
    }
  }
  function done(n, answer) {
    const j = jobs[n];
    if (!j) return;
    delete jobs[n]; clearTimeout(j.timer);
    const why = 'the CrossChat extension did not answer';
    if (!answer) answer = j.job.kind === 'send' ? Object.fromEntries((j.job.to || []).map((p) => [p, { ok: false, why }])) : { ok: false, why };
    api('/outbox/result', { job_id: j.job.id, answer });
  }
  window.addEventListener('message', (e) => {
    if (e.source !== window || !e.data || !['sent', 'modded', 'windowed'].includes(e.data.crosschat)) return;
    done(e.data.n, e.data.answer);
  });

  // ---- light and dark -------------------------------------------------------------------------------------------------
  const THEMES = { auto: ['◐', 'Theme: follows this device'], light: ['☀', 'Theme: light'], dark: ['☾', 'Theme: dark'] };
  function setTheme(next) {
    if (next === 'auto') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = next;
    store('theme', next); showTheme(); repaint();
  }
  function showTheme() {
    const now = document.documentElement.dataset.theme || 'auto';
    $('theme').textContent = THEMES[now][0];
    $('theme').title = THEMES[now][1] + ' (click to change)';
    $('theme').setAttribute('aria-label', THEMES[now][1]);
    document.querySelectorAll('[data-theme-pick]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.themePick === now)));
    document.querySelector('meta[name="theme-color"]').content = lightNow() ? '#f6f1e9' : '#0d141c';
  }
  $('theme').onclick = () => { const order = ['auto', 'light', 'dark'], now = document.documentElement.dataset.theme || 'auto'; setTheme(order[(order.indexOf(now) + 1) % 3]); };
  document.querySelectorAll('[data-theme-pick]').forEach((b) => { b.onclick = () => setTheme(b.dataset.themePick); });
  matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => { showTheme(); repaint(); });

  const nameColor = (c) => A.readable(c, lightNow()) || 'var(--text)';
  function repaint() {                            // after a theme change: platform colours and name colours
    drawPlatforms();
    document.querySelectorAll('.tag').forEach((t) => t.style.setProperty('--c', css(t.dataset.p)));
    list.querySelectorAll('.name').forEach((n) => { n.style.color = nameColor(n.dataset.color); });
    list.querySelectorAll('.emote.tw').forEach((img) => { img.src = img.src.replace(/\/(dark|light)\//, lightNow() ? '/light/' : '/dark/'); });
  }

  // The message text, with Twitch's emotes and 7TV / BetterTTV / FrankerFaceZ words swapped for their pictures.
  function words(into, m) {
    F.withEmotes(A.pieces(m.text, m.p === 'twitch' ? m.emotes : ''), emotes).forEach((piece) => {
      if (piece.text != null) { into.append(piece.text); return; }
      const img = el('img', piece.url ? 'emote' : 'emote tw'); img.alt = piece.alt; img.title = piece.alt; img.decoding = 'async';
      img.src = piece.url || 'https://static-cdn.jtvnw.net/emoticons/v2/' + piece.emote + '/default/' + (lightNow() ? 'light' : 'dark') + '/1.0';
      into.append(img);
    });
  }
  function rewords() {                            // the emote list changed: draw every message's words again
    list.querySelectorAll('.m[data-id] .words').forEach((w) => { const m = msgs.get(w.closest('.m').dataset.id); if (m) { w.textContent = ''; words(w, m); } });
  }

  // ---- who is watching, where a reply can go -------------------------------------------------------------------------
  const targets = () => A.targetsFor(ctx.states, replyTo, kickAuth.state);

  const STATE = { on: 'connected', waiting: 'waiting for the stream', retry: 'reconnecting' };
  function pillTitle(p) {
    const state = ctx.states[p], h = A.health(health[p]);
    const off = p === 'x' ? 'no livestream there (Go live on X starts one)'
      : A.PAGE_PLATFORMS.includes(p) ? 'its live page is not open (CrossChat opens it when you go live)' : 'off';
    return A.name(p) + ' chat: ' + (STATE[state] || (state === 'off' ? off : state)) + (h ? '\n' + h : '');
  }

  function drawPlatforms() {
    const bar = $('platforms'), only = $('targets');
    bar.textContent = ''; only.textContent = '';
    Object.keys(ctx.states).forEach((p) => {
      const state = ctx.states[p];
      const pill = el('div', 'pill ' + (state === 'on' ? 'on' : state === 'retry' ? 'retry' : ''));
      pill.dataset.p = p;
      pill.style.setProperty('--c', css(p));
      pill.title = pillTitle(p);
      pill.append(el('i'), el('span', '', A.name(p)), el('b', '', counts[p] == null ? '–' : counts[p]));
      bar.append(pill);
      if (!A.LIMIT[p]) return;
      const b = el('button', 'to'); b.type = 'button'; b.style.setProperty('--c', css(p)); b.append(el('i'), A.name(p));
      const can = A.takesReplies(p, kickAuth.state);
      b.disabled = sending || state !== 'on' || !can;
      b.title = !can ? 'Connect Kick in Settings to reply on Kick' : state === 'on' ? 'Send what you typed to ' + A.name(p) + ' only' : A.name(p) + ' chat is not open right now';
      b.onclick = () => post([p]);
      only.append(b, ' ');
    });
    drawEntry();
  }
  // "last message 8 s ago" goes stale: keep the tooltips and Settings → Connections current.
  setInterval(() => {
    document.querySelectorAll('#platforms .pill').forEach((pill) => { pill.title = pillTitle(pill.dataset.p); });
    if ($('settings').open) drawHealth();
  }, 5000);

  function drawEntry() {
    const to = targets(), text = A.clean(say.value), over = A.tooLong(text, to), n = [...text].length;
    $('left').textContent = !n ? '' : over.length ? n + ' characters: too long for ' + over.map((p) => A.name(p) + ' (' + A.LIMIT[p] + ')').join(', ') : n;
    $('left').className = over.length ? 'over' : '';
    $('all').textContent = sending ? 'Sending…' : replyTo ? 'Reply on ' + A.name(replyTo.p) : 'Send to all';
    $('all').disabled = $('send').disabled = sending || !to.length;
    $('all').title = $('send').title = to.length ? 'Goes to: ' + to.map(A.name).join(', ') : 'No chat is open right now';
    document.querySelectorAll('#quick .chip:not(.edit)').forEach((c) => { c.disabled = !A.openPlatforms(ctx.states, kickAuth.state).length; });
  }

  // ---- notes in the list ---------------------------------------------------------------------------------------------
  function note(text, tone) { add({ kind: 'note' + (tone ? ' ' + tone : ''), id: 'local-' + Date.now() + Math.random(), text, t: Date.now(), p: 'system' }); }

  // ---- replying and sending -----------------------------------------------------------------------------------------
  function setReply(m) {                          // reply to one message: the answer goes to its platform only
    list.querySelectorAll('.picked').forEach((row) => row.classList.remove('picked'));
    replyTo = m ? { p: m.p, id: (m.mid || m.id.replace(/^[a-z]+-/, '')), name: m.name, handle: m.handle || '' } : null;
    $('replying').className = m ? 'on' : '';
    if (m) {
      $('replying').firstChild.textContent = 'Replying to ' + m.name + ' on ' + A.name(m.p);
      const row = rowOf(m.id); if (row) row.classList.add('picked');
      const at = A.mention(m);
      if (!say.value.startsWith(at)) say.value = at + say.value;
      say.focus(); say.setSelectionRange(say.value.length, say.value.length);
    }
    drawPlatforms();
  }

  // Send `text` (the box when not given) to the platforms `to`. reply: answer one message (to has its platform only).
  async function post(to, text, reply) {
    const box = text == null;
    text = A.clean(box ? say.value : text);
    if (!text || (box && sending)) return;
    if (!to.length) return note('No chat is open to post to right now.', 'bad');
    const over = A.tooLong(text, to);
    if (over.length) return note('Too long for ' + over.map((p) => A.name(p) + ' (' + A.LIMIT[p] + ' characters)').join(', ') + '.', 'bad');
    if (box) { reply = replyTo && to.length === 1 && to[0] === replyTo.p ? replyTo : null; sending = true; drawPlatforms(); }
    if (to.length > 1) { echoes.push({ text, to, t: Date.now() }); if (echoes.length > 20) echoes.shift(); }
    const a = await api('/send', { to, text, reply: reply || null, dry: DRY });
    if (!a.ok || !a.job_id) {
      if (box) { sending = false; drawPlatforms(); }
      return note('Not sent: ' + (a.why || 'CrossChat did not answer') + '.', 'bad');
    }
    track(a.job_id, { kind: 'send', to, box });
  }

  say.addEventListener('input', drawEntry);
  say.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); post(targets()); }
    else if (e.key === 'Escape' && replyTo) setReply(null);
  });
  $('all').onclick = $('send').onclick = () => post(targets());
  $('cancel').onclick = () => { setReply(null); say.focus(); };

  // ---- featured, starred, moderation ----------------------------------------------------------------------------------
  async function featureIt(id) {
    const a = await api('/feature', { id: id || null });
    if (!a.ok) note(id ? 'Could not show that on stream: ' + (a.why || 'it is too old') + '.' : 'Could not hide the featured message.', 'bad');
  }
  function showFeatured(m) {
    featuredId = m ? m.id : null;
    list.querySelectorAll('.m.featured').forEach((row) => row.classList.remove('featured'));
    const row = m && rowOf(m.id); if (row) row.classList.add('featured');
    $('featured').hidden = !m;
    $('featured').querySelector('span').textContent = m ? m.name + (m.text ? ': ' + m.text : '') : '';
    list.querySelectorAll('.acts .show').forEach((b) => { b.textContent = b.closest('.m').dataset.id === featuredId ? 'hide' : 'show'; });
  }
  $('unfeature').onclick = () => featureIt(null);

  function toggleStar(id) {
    const on = !starred.has(id);
    if (on) starred.add(id); else starred.delete(id);
    drawStars();
    api('/star', { id, on }).then((a) => { if (!a.ok) note('Could not ' + (on ? 'star' : 'unstar') + ' that: ' + (a.why || 'no answer') + '.', 'bad'); });
  }
  function drawStars() {
    list.querySelectorAll('.m[data-id]').forEach((row) => {
      const on = starred.has(row.dataset.id);
      row.classList.toggle('starred', on);
      const flag = row.querySelector('.flag.star'); if (flag) flag.hidden = !on;
      const b = row.querySelector('.acts .star'); if (b) { b.textContent = on ? '★' : '☆'; b.classList.toggle('on', on); b.title = on ? 'Remove from Answer later' : 'Answer later'; }
    });
    drawViews();
  }

  async function moderate(m, entry, seconds) {
    const a = await api('/mod', { p: m.p, action: entry.action, message_id: m.mid || '', user_id: m.uid || '', name: m.name, seconds: seconds || 0, reason: '' });
    if (!a.ok || !a.job_id) return note(A.name(m.p) + ': ' + (a.why || 'CrossChat did not answer') + '.', 'bad');
    track(a.job_id, { kind: 'mod', p: m.p, action: entry.action, who: m.name, seconds });
  }

  // ---- the message list ---------------------------------------------------------------------------------------------
  const rowOf = (id) => list.querySelector('.m[data-id="' + CSS.escape(id) + '"]');
  function tagFor(p) { const tag = el('div', 'tag', A.NAMES[p] ? A.NAMES[p][1] : '?'); tag.dataset.p = p; tag.style.setProperty('--c', css(p)); return tag; }

  // A viewer's name in the list: a button that opens their card (their messages now and in earlier streams).
  function nameButton(m, text) {
    const b = el(m.name && A.NAMES[m.p] ? 'button' : 'span', 'name', text || m.name);
    b.dataset.color = m.color || ''; b.style.color = nameColor(m.color);
    if (b.tagName === 'BUTTON') {
      b.type = 'button'; b.title = 'See ' + m.name + '’s messages';
      b.onclick = (e) => { e.stopPropagation(); openViewer(m); };
    }
    return b;
  }

  // A sub, gift, raid, cheer, Super Chat or Rant: its type, the same sentence the alerts widget shows (name and amount
  // picked out) and what the viewer wrote, alike for every platform.
  function eventBody(into, m) {
    const a = T.alertParts(m, null, A.name(m.p));
    const kind = el('span', 'akind', A.alertWord(a.kind)); kind.dataset.alert = a.kind;
    into.append(kind);
    const line = el('span', 'system');
    a.parts.forEach((part) => {
      if (part.key === 'name' && m.name) line.append(nameButton(m, part.value));
      else if (part.key === 'amount') line.append(el('b', 'amount', part.value));
      else line.append(part.text !== undefined ? part.text : part.value);
    });
    into.append(line);
    if (a.words) { into.append(' · '); const said = el('span', 'words'); words(said, m); into.append(said); }
  }

  function add(m) {
    const empty = $('empty'); if (empty && view === 'all') empty.hidden = true;
    const row = el('div', 'm ' + m.kind); row.dataset.id = m.id; row.dataset.who = m.p + ':' + (m.name || '').toLowerCase();
    if (m.kind.startsWith('note')) { row.textContent = m.text; list.append(row); scrolled(); drawViews(); return; }
    // My own line, sent to several platforms, comes back once from each: it stays one row and gains a tag.
    const mine = m.kind === 'chat' && echoes.find((s) => s.text === m.text && s.to.includes(m.p) && Date.now() - s.t < 30000);
    if (mine && mine.row && mine.row.isConnected) {
      if (!mine.seen.includes(m.p)) { mine.seen.push(m.p); mine.row.firstChild.append(tagFor(m.p)); }
      return;
    }
    if (mine) { mine.row = row; mine.seen = [m.p]; }
    msgs.set(m.id, m);
    if (msgs.size > 600) msgs.delete(msgs.keys().next().value);
    row.tabIndex = -1;
    row.setAttribute('aria-label', m.name + ' on ' + A.name(m.p) + (m.first === 'ever' ? ', first message in your channel' : '') + ': '
      + (m.kind === 'event' ? T.alertLine(m, null, A.name(m.p)) : m.text) + (m.hidden ? ' (hidden by your filters)' : ''));
    if (m.question) row.classList.add('q');
    if (m.first === 'ever') row.classList.add('first');
    const tag = el('div', 'tags'); tag.append(tagFor(m.p));
    const body = el('div', 'body');
    (m.badges || []).filter((b) => /^(broadcaster|owner|moderator|vip|verified|member|subscriber|founder)$/.test(b))
      .forEach((b) => body.append(el('span', 'badge', b === 'broadcaster' || b === 'owner' ? 'you' : b === 'moderator' ? 'mod' : b === 'subscriber' ? 'sub' : b)));
    if (m.kind === 'event') eventBody(body, m);
    else {
      body.append(nameButton(m));
      const said = el('span', 'words'); words(said, m); body.append(said);
    }
    body.append(el('span', 'time', new Date(m.t).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })));
    const flags = el('span', 'flags');
    if (FIRST[m.first]) { const f = el('span', 'flag first', FIRST[m.first][0]); f.title = FIRST[m.first][1]; flags.append(f); }
    if (m.question) flags.append(el('span', 'flag q', 'Q'));
    const star = el('span', 'flag star', '★'); star.hidden = !starred.has(m.id); flags.append(star);
    body.append(flags);
    if (m.hidden) hideRow(row, m.hidden, flags);
    row.append(tag, body);
    if (m.name && A.NAMES[m.p]) {                 // the hover toolbar (devices with a mouse); touch opens the sheet instead
      const acts = el('div', 'acts');
      const can = A.canReply(m, ctxNow());
      if (A.LIMIT[m.p] && m.kind === 'chat') {
        const re = el('button', 're', 'reply'); re.type = 'button'; re.disabled = !can.ok;
        re.title = can.ok ? 'Reply to ' + m.name + ' on ' + A.name(m.p) : can.why;
        re.onclick = (e) => { e.stopPropagation(); setReply(m); };
        acts.append(re);
      }
      const show = el('button', 'show', m.id === featuredId ? 'hide' : 'show'); show.type = 'button';
      show.title = 'Show this message big on stream (featured message)';
      if (m.hidden && m.id !== featuredId) { show.disabled = true; show.title = 'Hidden by your filters, so it stays off the stream'; }
      show.onclick = (e) => { e.stopPropagation(); featureIt(m.id === featuredId ? null : m.id); };
      const st = el('button', 'star' + (starred.has(m.id) ? ' on' : ''), starred.has(m.id) ? '★' : '☆'); st.type = 'button';
      st.title = starred.has(m.id) ? 'Remove from Answer later' : 'Answer later';
      st.onclick = (e) => { e.stopPropagation(); toggleStar(m.id); };
      const more = el('button', 'more', '⋯'); more.type = 'button'; more.title = 'More: quick reply, moderation, copy';
      more.setAttribute('aria-label', 'More actions for this message'); more.setAttribute('aria-haspopup', 'dialog');
      more.onclick = (e) => { e.stopPropagation(); openSheet(m); };
      acts.append(show, st, more);
      row.append(acts);
      row.addEventListener('click', (e) => { if (touch.matches && !e.target.closest('button, a')) openSheet(m); });
      row.addEventListener('contextmenu', (e) => { if (!touch.matches) { e.preventDefault(); openSheet(m); } });
    }
    if (starred.has(m.id)) row.classList.add('starred');
    if (featuredId === m.id) row.classList.add('featured');
    list.append(row);
    let extra = list.querySelectorAll('.m').length - 400;    // keep 400 rows, but never drop a starred one
    for (let r = list.querySelector('.m'); extra > 0 && r;) { const next = r.nextElementSibling; if (!r.classList.contains('starred')) { r.remove(); extra--; } r = next; }
    scrolled();
    drawViews();
    if (ding && !m.hidden && Date.now() - m.t < 5000) beep();
  }

  const FIRST = { ever: ['NEW', 'First message in your channel'], stream: ['1ST', 'First message this stream'] };
  const HIDDEN = { word: ['word', 'it has a word from your filter list'], user: ['viewer', 'you filtered this viewer'],
                   command: ['command', 'it is a !command'], bot: ['bot', 'it came from a bot'] };

  // A message the streamer's filters hide: dimmed here, with why. It never reaches the stream and is never read aloud.
  function hideRow(row, why, flags) {
    const [word, reason] = HIDDEN[why] || ['filter', 'it matched your filters'];
    row.classList.add('hid');
    flags = flags || row.querySelector('.flags');
    if (!flags || flags.querySelector('.flag.hid')) return;
    const f = el('span', 'flag hid', 'hidden · ' + word); f.title = 'Not on stream and not read aloud: ' + reason;
    flags.prepend(f);
    const show = row.querySelector('.acts .show');
    if (show && show.textContent === 'show') { show.disabled = true; show.title = 'Hidden by your filters, so it stays off the stream'; }
  }
  // Every row from one viewer (name or @handle, on any platform unless p is given), e.g. after "Filter this user".
  function hideWho(who, why, p) {
    who = String(who || '').toLowerCase().replace(/^@/, '');
    if (!who) return;
    msgs.forEach((m) => {
      if ((p && m.p !== p) || (String(m.name || '').toLowerCase() !== who && String(m.handle || '').toLowerCase() !== who)) return;
      m.hidden = m.hidden || why;
      const row = rowOf(m.id); if (row) hideRow(row, m.hidden);
    });
  }

  function scrolled() { if (pinned) list.scrollTop = list.scrollHeight; else jump.style.display = 'block'; }

  function beep() {
    try {
      audio = audio || new AudioContext();
      const o = audio.createOscillator(), g = audio.createGain();
      o.frequency.value = 880; o.type = 'sine'; g.gain.setValueAtTime(0.0001, audio.currentTime);
      g.gain.exponentialRampToValueAtTime(0.18, audio.currentTime + 0.01); g.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + 0.35);
      o.connect(g).connect(audio.destination); o.start(); o.stop(audio.currentTime + 0.4);
    } catch (e) { /* no sound on this device */ }
  }

  list.addEventListener('scroll', () => { pinned = list.scrollHeight - list.scrollTop - list.clientHeight < 60; if (pinned) jump.style.display = 'none'; });
  jump.onclick = () => { list.scrollTop = list.scrollHeight; };

  // Keyboard: arrows move between messages, Enter opens a message's actions, r replies, s stars.
  list.tabIndex = 0;
  list.addEventListener('keydown', (e) => {
    const rows = [...list.querySelectorAll('.m[tabindex]')].filter((r) => r.offsetParent);
    if (!rows.length) return;
    const at = rows.indexOf(document.activeElement);
    const go = (i) => { const r = rows[Math.max(0, Math.min(rows.length - 1, i))]; r.focus(); r.scrollIntoView({ block: 'nearest' }); };
    if (e.key === 'ArrowDown') { e.preventDefault(); go(at < 0 ? rows.length - 1 : at + 1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); go(at < 0 ? rows.length - 1 : at - 1); }
    else if (e.key === 'Home') { e.preventDefault(); go(0); }
    else if (e.key === 'End') { e.preventDefault(); go(rows.length - 1); }
    else if (at >= 0) {
      const m = msgs.get(rows[at].dataset.id);
      if (!m) return;
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openSheet(m); }
      else if (e.key === 'r' && A.canReply(m, ctxNow()).ok) { e.preventDefault(); setReply(m); }
      else if (e.key === 's') { e.preventDefault(); toggleStar(m.id); }
    }
  });

  // ---- views: all, questions, answer later ---------------------------------------------------------------------------
  const EMPTY = { all: ['No messages yet.', 'Chat from every platform the stream goes to lands here.'],
                  questions: ['No questions yet.', 'Messages that ask something collect here.'],
                  starred: ['Nothing saved for later.', 'Star a message (☆) to keep it here until you answer it.'] };
  function drawViews() {
    list.dataset.view = view;
    document.querySelectorAll('#views [role="tab"]').forEach((b) => { b.setAttribute('aria-selected', String(b.dataset.view === view)); b.tabIndex = b.dataset.view === view ? 0 : -1; });
    const qs = list.querySelectorAll('.m.q').length, ss = list.querySelectorAll('.m.starred').length;
    $('count-questions').textContent = qs || ''; $('count-starred').textContent = ss || '';
    const shown = view === 'all' ? list.querySelectorAll('.m').length : view === 'questions' ? qs : ss;
    const empty = $('empty');
    empty.hidden = shown > 0;
    empty.textContent = ''; empty.append(EMPTY[view][0], el('br'), EMPTY[view][1]);
  }
  document.querySelectorAll('#views [role="tab"]').forEach((b) => {
    b.onclick = () => { view = b.dataset.view; drawViews(); list.scrollTop = list.scrollHeight; };
    b.onkeydown = (e) => {
      const tabs = [...document.querySelectorAll('#views [role="tab"]')], i = tabs.indexOf(b);
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { const t = tabs[(i + (e.key === 'ArrowRight' ? 1 : 2)) % 3]; t.focus(); t.click(); }
    };
  });

  // ---- quick replies ----------------------------------------------------------------------------------------------------
  function drawQuick() {
    const bar = $('quick'); bar.textContent = '';
    quick.forEach((text) => {
      const chip = el('button', 'chip', text); chip.type = 'button';
      chip.title = 'Send "' + text + '" to every live chat (hold or right-click to put it in the box)';
      let held = false, timer = null;
      const put = () => { held = true; say.value = (say.value ? say.value.replace(/\s*$/, ' ') : '') + text; drawEntry(); say.focus(); };
      chip.addEventListener('pointerdown', () => { held = false; clearTimeout(timer); timer = setTimeout(put, 500); });
      ['pointerup', 'pointerleave', 'pointercancel'].forEach((ev) => chip.addEventListener(ev, () => clearTimeout(timer)));
      chip.addEventListener('contextmenu', (e) => { e.preventDefault(); clearTimeout(timer); if (!held) put(); });
      chip.addEventListener('click', () => { if (held) { held = false; return; } post(A.openPlatforms(ctx.states, kickAuth.state), text); });
      bar.append(chip);
    });
    const edit = el('button', 'chip edit', quick.length ? '✎' : '✎ Quick replies'); edit.type = 'button';
    edit.title = 'Edit quick replies'; edit.setAttribute('aria-label', 'Edit quick replies'); edit.setAttribute('aria-haspopup', 'dialog');
    edit.onclick = openQuickEditor;
    bar.append(edit);
    drawEntry();
  }

  function openQuickEditor() {
    const ul = $('qlist'); ul.textContent = '';
    const row = (text) => {
      const li = el('li'), input = el('input'); input.type = 'text'; input.maxLength = A.QUICK_LENGTH; input.value = text; input.setAttribute('aria-label', 'Quick reply');
      const up = el('button', 'icon-btn', '↑'), down = el('button', 'icon-btn', '↓'), del = el('button', 'icon-btn', '✕');
      [up, down, del].forEach((b) => { b.type = 'button'; });
      up.setAttribute('aria-label', 'Move up'); down.setAttribute('aria-label', 'Move down'); del.setAttribute('aria-label', 'Remove');
      up.onclick = () => { if (li.previousElementSibling) ul.insertBefore(li, li.previousElementSibling); up.focus(); };
      down.onclick = () => { if (li.nextElementSibling) ul.insertBefore(li.nextElementSibling, li); down.focus(); };
      del.onclick = () => { li.remove(); };
      li.append(input, up, down, del); ul.append(li);
      return input;
    };
    quick.forEach(row);
    $('qadd').onclick = () => { if (ul.children.length < A.QUICK_MAX) row('').focus(); };
    $('qsave').onclick = async () => {
      const replies = A.cleanQuick([...ul.querySelectorAll('input')].map((i) => i.value));
      const a = await api('/quick', { replies });
      if (a.ok) { quick = replies; drawQuick(); $('quick-edit').close(); } else note('Quick replies not saved: ' + (a.why || 'no answer') + '.', 'bad');
    };
    openDialog($('quick-edit'));
  }

  // ---- the action sheet for one message ------------------------------------------------------------------------------
  const ctxNow = () => ({ remote: ctx.remote, executor: ctx.executor || DEMO, twitch: twitchAuth.state, kick: kickAuth.state, states: ctx.states });

  // After Twitch, Kick or the chat window comes or goes: what each row's reply button can do now.
  function refreshActs() {
    const c = ctxNow();
    list.querySelectorAll('.acts .re').forEach((b) => {
      const m = msgs.get(b.closest('.m').dataset.id); if (!m) return;
      const can = A.canReply(m, c);
      b.disabled = !can.ok; b.title = can.ok ? 'Reply to ' + m.name + ' on ' + A.name(m.p) : can.why;
    });
  }

  function item(icon, label, how, action, opts) {
    opts = opts || {};
    const li = el('li'), b = el('button', 'item' + (opts.danger ? ' danger' : '')); b.type = 'button';
    const text = el('span'); text.append(label);
    if (!how.ok && how.why) text.append(el('small', '', how.why));
    else if (opts.hint) text.append(el('small', '', opts.hint));
    b.append(el('span', 'ico', icon), text);
    if (!how.ok) b.setAttribute('aria-disabled', 'true');
    b.onclick = () => { if (how.ok) action(); };
    li.append(b);
    return li;
  }

  function group(menu, label) { const li = el('li', 'group'); li.append(el('div', 'label', label)); menu.append(li); }

  function openSheet(m) {
    const menu = $('sheet-menu'), quote = $('sheet-quote'), c = ctxNow();
    $('sheet-title').textContent = m.name + ' · ' + A.name(m.p);
    quote.textContent = ''; quote.append(tagFor(m.p));
    if (m.kind === 'event') quote.append(el('b', '', T.alertLine({ ...m, text: '' }, null, A.name(m.p)) + (m.text ? ' · ' : '')));
    words(quote, m);
    menu.textContent = '';
    const close = () => $('sheet').close();
    const can = A.canReply(m, c), yes = { ok: true };
    menu.append(item('↩', 'Reply', can, () => { close(); setReply(m); }));
    const on = m.id === featuredId;
    menu.append(item('▣', on ? 'Hide from stream' : 'Show on stream', on || !m.hidden ? yes : { ok: false, why: 'Hidden by your filters, so it stays off the stream' },
      () => { close(); featureIt(on ? null : m.id); }, { hint: on ? '' : 'Big, as the featured message' }));
    const st = starred.has(m.id);
    menu.append(item(st ? '★' : '☆', st ? 'Remove from Answer later' : 'Answer later', yes, () => { close(); toggleStar(m.id); }));
    menu.append(item('🔊', 'Read aloud', m.hidden ? { ok: false, why: 'Hidden by your filters, so it is never read aloud' } : yes, () => { close(); readAloud(m); },
      { hint: 'On the streaming PC’s speakers' }));
    menu.append(item('⧉', 'Copy text', yes, () => { close(); copy((m.system ? m.system + ' ' : '') + m.text); }));
    if (m.name && A.NAMES[m.p]) {
      menu.append(item('👤', 'View viewer', yes, () => { close(); openViewer(m); }, { hint: 'Their messages this stream and in earlier ones' }));
      menu.append(filterItem(m, close));
    }
    group(menu, 'Moderate');
    modItems(menu, m, c, close);
    if (A.LIMIT[m.p] && m.kind === 'chat') {
      group(menu, 'Quick reply to ' + m.name);
      if (!quick.length) menu.append(item('✎', 'Add quick replies', yes, () => { close(); openQuickEditor(); }));
      quick.slice(0, 6).forEach((text) => {
        menu.append(item('»', text, can, () => { close(); post([m.p], A.mention(m) + text, { p: m.p, id: m.mid || m.id.replace(/^[a-z]+-/, ''), name: m.name, handle: m.handle || '' }); }));
      });
    }
    list.querySelectorAll('.m.open').forEach((r) => r.classList.remove('open'));
    const row = rowOf(m.id); if (row) row.classList.add('open');
    openDialog($('sheet'));
    const first = menu.querySelector('.item:not([aria-disabled])');
    if (first && byKeyboard) first.focus();
  }
  $('sheet').addEventListener('close', () => list.querySelectorAll('.m.open').forEach((r) => r.classList.remove('open')));

  // "Filter this user" (or stop filtering them), for the action sheet and the viewer card.
  function filterItem(m, close) {
    const filtered = filters.users.some((u) => [m.name, m.handle].some((n) => n && n.toLowerCase() === u.toLowerCase().replace(/^@/, '')));
    return item('⊘', filtered ? 'Stop filtering ' + m.name : 'Filter this user', ctx.remote ? { ok: false, why: 'Filters are set on the streaming PC' } : { ok: true },
      () => { close(); filterUser(m, !filtered); }, { hint: filtered ? '' : 'Hide their messages here and on stream' });
  }

  // The moderation entries for message m (delete, timeouts, ban, unban), each asking first where it should.
  function modItems(menu, m, c, close) {
    A.modMenu(m, c).forEach((entry) => {
      const icon = { delete: '🗑', timeout: '⏱', mute: '🔇', ban: '⛔', unban: '↺' }[entry.action] || '•';
      menu.append(item(icon, entry.label, entry, async () => {
        close();
        if (entry.custom) {
          const kick = m.p === 'kick';
          $('confirm-input').max = kick ? 10080 : 20160;
          const minutes = await ask({ title: 'Time out ' + m.name, text: 'How long on ' + A.name(m.p) + '? (1 minute to ' + (kick ? '7' : '14') + ' days)', ok: 'Time out', input: true });
          if (minutes) moderate(m, entry, A.timeoutSeconds(m.p, minutes));
        } else if (entry.action === 'ban') {
          const ban = m.p === 'youtube' ? { title: 'Hide ' + m.name + '?', text: 'They won\'t be able to chat on your channel until you unhide them in YouTube Studio.', ok: 'Hide user' }
            : m.p === 'rumble' ? { title: 'Mute ' + m.name + ' forever?', text: 'They won\'t be able to chat on your Rumble channel until you unmute them under Muted users in Rumble\'s chat.', ok: 'Mute forever' }
            : { title: 'Ban ' + m.name + '?', text: 'They won\'t be able to chat on your ' + A.name(m.p) + ' channel until you unban them.', ok: 'Ban' };
          if (await ask(ban)) moderate(m, entry, 0);
        } else moderate(m, entry, entry.seconds || 0);
      }, { danger: entry.danger }));
    });
  }

  function copy(text) {
    const fallback = () => {                      // the companion runs on plain http, where the clipboard API is off
      const t = el('textarea'); t.value = text; t.style.cssText = 'position:fixed;opacity:0'; document.body.append(t); t.select();
      try { document.execCommand('copy'); note('Copied.', 'good'); } catch (e) { note('Could not copy here.', 'bad'); }
      t.remove();
    };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(() => note('Copied.', 'good'), fallback); else fallback();
  }

  // A small confirm (or number) dialog: resolves true / the number, or null when cancelled.
  function ask(o) {
    return new Promise((resolve) => {
      const d = $('confirm');
      $('confirm-title').textContent = o.title; $('confirm-text').textContent = o.text || '';
      $('confirm-field').hidden = !o.input; $('confirm-yes').textContent = o.ok || 'OK';
      let answer = null;
      $('confirm-yes').onclick = () => { answer = o.input ? Number($('confirm-input').value) || null : true; d.close(); };
      $('confirm-no').onclick = () => d.close();
      d.addEventListener('close', () => resolve(answer), { once: true });
      d.showModal();
      (o.input ? $('confirm-input') : $('confirm-no')).focus();
    });
  }

  // Dialogs opened with a mouse or a finger don't start on a focus ring; opened from the keyboard they do.
  let byKeyboard = false;
  document.addEventListener('keydown', () => { byKeyboard = true; }, true);
  document.addEventListener('pointerdown', () => { byKeyboard = false; }, true);
  function openDialog(d) {
    d.showModal();
    if (!byKeyboard && d.contains(document.activeElement) && document.activeElement.matches('[data-close]')) document.activeElement.blur();
  }
  document.querySelectorAll('dialog [data-close]').forEach((b) => { b.onclick = () => b.closest('dialog').close(); });
  document.querySelectorAll('dialog').forEach((d) => d.addEventListener('click', (e) => { if (e.target === d) d.close(); }));   // a tap outside closes

  // ---- settings ------------------------------------------------------------------------------------------------------
  const showDing = () => { $('ding').textContent = 'Ding: ' + (ding ? 'on' : 'off'); $('ding-switch').checked = ding; };
  const setDing = (on) => { ding = on; store('ding', on ? '1' : '0'); showDing(); if (on) beep(); };
  $('ding').onclick = () => setDing(!ding);
  $('ding-switch').onchange = () => setDing($('ding-switch').checked);
  $('gear').onclick = () => { drawSettings(); openDialog($('settings')); };
  $('studio').onclick = $('studio-open').onclick = () => window.open('/studio', '_blank');
  document.querySelectorAll('[data-test]').forEach((b) => {
    b.onclick = async () => { const a = await api('/test', { kind: b.dataset.test }); note(a.ok ? 'Test ' + b.dataset.test + ' sent to the widgets in OBS.' : 'Test not sent: ' + (a.why || 'no answer') + '.', a.ok ? 'good' : 'bad'); };
  });

  function drawTwitch() {
    const s = twitchAuth.state;
    $('twitch-dot').className = 'dot' + (s === 'on' ? ' ok' : '');
    $('twitch-state').textContent = s === 'on' ? 'Connected' + (twitchAuth.login ? ' as ' + twitchAuth.login : '') : s === 'pending' ? 'Waiting for you to approve CrossChat on Twitch…'
      : s === 'error' ? 'Not connected: ' + (twitchAuth.why || 'Twitch said no') : 'Not connected';
    $('twitch-pending').hidden = s !== 'pending';
    $('twitch-code').textContent = twitchAuth.user_code || '';
    const blocked = s === 'off' && !!twitchAuth.why;      // e.g. this CrossChat has no Twitch app Client ID
    $('twitch-connect').hidden = ctx.remote || s === 'on' || s === 'pending';
    $('twitch-connect').disabled = blocked;
    $('twitch-connect').title = blocked ? twitchAuth.why : '';
    $('twitch-disconnect').hidden = ctx.remote || s !== 'on';
    $('twitch-hint').textContent = blocked ? twitchAuth.why + ' Until Twitch is connected, CrossChat reads Twitch chat but can’t reply or moderate there.'
      : ctx.remote ? 'Connecting Twitch is done on the streaming PC (Settings there).'
      : s === 'on' ? 'CrossChat posts your Twitch replies and moderates Twitch chat through Twitch’s official API.'
      : 'Connect Twitch to reply and moderate on Twitch. CrossChat uses Twitch’s official API for both.';
  }
  $('twitch-connect').onclick = async () => { const a = await api('/twitch/connect', {}); if (!a.ok) note('Twitch: ' + (a.why || 'could not start') + '.', 'bad'); };
  $('twitch-disconnect').onclick = async () => { if (await ask({ title: 'Disconnect Twitch?', text: 'CrossChat then reads Twitch chat but can’t reply or moderate there until you connect again.', ok: 'Disconnect' })) api('/twitch/disconnect', {}); };
  $('twitch-open').onclick = () => window.open(/^https:\/\/www\.twitch\.tv\//.test(twitchAuth.verification_uri || '') ? twitchAuth.verification_uri
    : 'https://www.twitch.tv/activate', '_blank', 'noopener');

  // Kick: replies and moderation through Kick's official API once the streamer approves CrossChat on kick.com.
  let kickWanted = false, kickOpened = '';
  function openKick(url) {
    if (!/^https:\/\//.test(url || '') || kickOpened === url) return;
    kickOpened = url; window.open(url, '_blank', 'noopener');
  }
  function drawKick() {
    const s = kickAuth.state;
    $('kick-dot').className = 'dot' + (s === 'on' ? ' ok' : '');
    $('kick-state').textContent = s === 'on' ? 'Connected' + (kickAuth.login ? ' as ' + kickAuth.login : '') : s === 'pending' ? 'Waiting for you to approve CrossChat on Kick…'
      : s === 'error' ? 'Not connected: ' + (kickAuth.why || 'Kick said no') : 'Not connected';
    const blocked = s === 'off' && !!kickAuth.why;
    $('kick-open').hidden = s !== 'pending' || ctx.remote || !kickAuth.url;
    $('kick-connect').hidden = ctx.remote || s === 'on' || s === 'pending';
    $('kick-connect').disabled = blocked;
    $('kick-connect').title = blocked ? kickAuth.why : '';
    $('kick-disconnect').hidden = ctx.remote || s !== 'on';
    $('kick-hint').textContent = blocked ? kickAuth.why + ' Kick chat is still read; replies and moderation need the connection.'
      : ctx.remote ? 'Connecting Kick is done on the streaming PC (Settings there).'
      : s === 'on' ? 'CrossChat posts your Kick replies and moderates Kick chat through Kick’s official API.'
      : s === 'pending' ? 'Approve CrossChat in the Kick tab that opened, then come back here.'
      : 'Connect Kick to reply and moderate on Kick. CrossChat uses Kick’s official API for both.';
  }
  $('kick-connect').onclick = async () => {
    kickWanted = true; kickOpened = '';
    const a = await api('/kick/connect', {});
    if (!a.ok) { kickWanted = false; note('Kick: ' + (a.why || 'could not start') + '.', 'bad'); } else if (a.url) openKick(a.url);
  };
  $('kick-disconnect').onclick = async () => { if (await ask({ title: 'Disconnect Kick?', text: 'CrossChat then reads Kick chat but can’t reply or moderate there until you connect again.', ok: 'Disconnect' })) api('/kick/disconnect', {}); };
  $('kick-open').onclick = () => { kickOpened = ''; openKick(kickAuth.url); };

  // Rumble: chat, Rants, subs and viewers from Rumble's official Live Stream API (a private URL the streamer pastes, kept
  // encrypted by the hub); replies are typed into Rumble's own chat window.
  function drawRumble() {
    const s = rumbleAuth.state;
    $('rumble-dot').className = 'dot' + (s === 'on' ? ' ok' : '');
    $('rumble-state').textContent = s === 'on' ? 'Connected' : s === 'error' ? 'Not connected: ' + (rumbleAuth.why || 'Rumble said no') : 'Not connected';
    $('rumble-form').hidden = ctx.remote || s === 'on';
    $('rumble-disconnect').hidden = ctx.remote || s !== 'on';
    $('rumble-hint').textContent = ctx.remote ? 'Connecting Rumble is done on the streaming PC (Settings there).'
      : s === 'on' ? 'CrossChat reads Rumble through its official API. When your Rumble live starts, Rumble’s chat window opens; replies are typed there as you (sign in to Rumble in this browser).'
      : 'Paste your Live Stream API URL from rumble.com/account/livestream-api. CrossChat reads Rumble chat, Rants, subs and viewers through it, and keeps it encrypted on this PC.';
  }
  $('rumble-connect').onclick = async () => {
    const url = $('rumble-url').value.trim();
    if (!url) return;
    const a = await api('/rumble/connect', { url });
    $('rumble-url').value = '';
    if (!a.ok) note('Rumble: ' + (a.why || 'could not connect'), 'bad');
  };
  $('rumble-disconnect').onclick = async () => { if (await ask({ title: 'Disconnect Rumble?', text: 'CrossChat then deletes the Rumble API URL from this PC and stops reading Rumble chat.', ok: 'Disconnect' })) api('/rumble/disconnect', {}); };

  // Discord: posts to one channel of the streamer's server through a webhook (kept encrypted by the hub, never shown
  // again): a going-live notice, the messages shown on stream and, if picked, all chat.
  function drawDiscord() {
    const s = discordAuth.state, on = s === 'on';
    $('discord-dot').className = 'dot' + (on ? ' ok' : '');
    $('discord-state').textContent = on ? 'Connected' + (discordAuth.name ? ': posts as ' + discordAuth.name : '')
      : s === 'error' ? 'Not connected: ' + (discordAuth.why || 'Discord said no') : 'Not connected';
    $('discord-form').hidden = ctx.remote || on;
    $('discord-choices').hidden = ctx.remote || !on;
    $('discord-test').hidden = $('discord-disconnect').hidden = ctx.remote || !on;
    document.querySelectorAll('[data-discord]').forEach((box) => { box.checked = discordAuth[box.dataset.discord] === true; });
    $('discord-hint').textContent = ctx.remote ? 'Connecting Discord is done on the streaming PC (Settings there).'
      : on ? 'Posted only while you’re live, and only what viewers see on stream: never hidden messages. Chat can’t ping anyone, and links in it can’t be clicked there.'
      : 'Post to a channel of your Discord server while you’re live. In Discord: Server Settings → Integrations → Webhooks → New Webhook → Copy Webhook URL, then paste it here.';
  }
  $('discord-connect').onclick = async () => {
    const url = A.clean($('discord-url').value);
    if (!url) return;
    if (!A.discordWebhook(url)) { note('Discord: that isn’t a webhook URL. In Discord, use Copy Webhook URL.', 'bad'); return; }
    const a = await api('/discord/connect', { url, live: true, featured: true, chat: false });
    $('discord-url').value = '';
    if (!a.ok) note('Discord: ' + (a.why || 'could not connect'), 'bad');
  };
  document.querySelectorAll('[data-discord]').forEach((box) => {
    box.onchange = () => api('/discord/options', { [box.dataset.discord]: box.checked });
  });
  $('discord-test').onclick = async () => {
    const a = await api('/discord/test', {});
    note(a.ok ? 'Discord: test post sent. Check the channel.' : 'Discord: ' + (a.why || 'the test post failed'), a.ok ? '' : 'bad');
  };
  $('discord-disconnect').onclick = async () => { if (await ask({ title: 'Disconnect Discord?', text: 'CrossChat then deletes the webhook URL from this PC and posts nothing more. To stop the webhook everywhere, delete it in Discord too.', ok: 'Disconnect' })) api('/discord/disconnect', {}); };

  // The companion away from home: Tailscale on this PC and the phone, then the pairing QR code uses this PC's Tailscale address.
  function drawTailscale() {
    $('tailscale-switch').checked = companion.tailscale === true;
    $('tailscale-hint').textContent = !companion.tailscale
      ? 'For the companion away from home, install Tailscale (tailscale.com, free for personal use) on this PC and the phone, sign in to the same account on both, and switch this on.'
      : companion.why ? companion.why
      : companion.address ? 'Tailscale is on (this PC is ' + companion.address + '). Pair the phone (again) with Tailscale on there too: the code then works at home and away.'
      : 'Looking for Tailscale on this PC…';
  }
  $('tailscale-switch').onchange = async () => {
    const a = await api('/companion/tailscale', { on: $('tailscale-switch').checked });
    if (!a.ok) { note('Tailscale: ' + (a.why || 'could not change it'), 'bad'); drawTailscale(); }
  };

  // The update notice (off unless switched on): a line with a link to the newer release's page on GitHub.
  const hiddenUpdate = () => { try { return localStorage.getItem('update-hidden') || ''; } catch (e) { return ''; } };
  function drawUpdate() {
    $('update-check').checked = update.check === true;
    const link = A.releaseLink(update.url);
    $('update').hidden = ctx.remote || !update.check || !link || !update.version || hiddenUpdate() === update.version;
    if ($('update').hidden) return;
    $('update').querySelector('span').textContent = 'CrossChat ' + update.version + ' is out (this is ' + (ctx.version || 'older') + ').';
    $('update-link').href = link;
  }
  $('update-check').onchange = async () => {
    const a = await api('/updates', { check: $('update-check').checked });
    if (!a.ok) { note('Update notice: ' + (a.why || 'could not change it'), 'bad'); drawUpdate(); }
  };
  $('update-hide').onclick = () => { try { localStorage.setItem('update-hidden', update.version || ''); } catch (e) { /* storage blocked: hidden until reload */ } $('update').hidden = true; };

  // How each chat connection is doing: how long it has been up, when the last message came, how often it reconnected.
  function drawHealth() {
    const ul = $('health'); ul.textContent = '';
    const ps = Object.keys(ctx.states);
    if (!ps.length) ul.append(el('li', 'none', 'No chats yet: they appear when CrossChat starts reading them.'));
    ps.forEach((p) => {
      const li = el('li'), state = ctx.states[p];
      const dot = el('i', 'dot' + (state === 'on' ? ' ok' : state === 'retry' ? '' : ' off'));
      li.append(dot, el('b', '', A.name(p)), el('span', '', A.health(health[p]) || STATE[state] || state));
      ul.append(li);
    });
  }

  function drawDevices() {
    const ul = $('devices'); ul.textContent = '';
    if (!devices.length) ul.append(el('li', '', 'None yet.'));
    const day = (t) => (t ? new Date(t < 1e12 ? t * 1000 : t).toLocaleDateString([], { month: 'short', day: 'numeric' }) : '–');
    devices.forEach((d) => {
      const li = el('li'), info = el('div');
      info.append(d.name || 'Device', el('small', '', 'paired ' + day(d.created) + ' · last seen ' + day(d.last_seen)));
      const b = el('button', 'btn', 'Remove'); b.type = 'button'; b.setAttribute('aria-label', 'Remove ' + (d.name || 'device'));
      b.onclick = async () => { if (await ask({ title: 'Remove ' + (d.name || 'this device') + '?', text: 'It stops reading and answering chat until it is paired again.', ok: 'Remove' })) api('/devices/revoke', { id: d.id }); };
      li.append(info, b); ul.append(li);
    });
  }
  $('pair-start').onclick = async () => {
    const a = await api('/pair/start', {});
    if (a.ok && a.code) showPair(a);              // the answer has it too; the `pair` event follows for other windows
    else if (!a.ok) note('Pairing: ' + (a.why || 'could not start') + '.', 'bad');
  };

  function showPair(p) {
    clearInterval(pairTimer);
    $('pair').hidden = !p;
    if (!p) return;
    $('pair-code').textContent = p.code; $('pair-url').textContent = p.url;
    drawQr($('pair-qr'), p.url);
    const tick = () => {
      const left = A.secondsLeft(p.expires);
      $('pair-left').textContent = left ? 'Code works for ' + Math.floor(left / 60) + ':' + String(left % 60).padStart(2, '0') : 'Code expired. Press Pair a device again.';
      if (!left) { clearInterval(pairTimer); $('pair-qr').textContent = ''; }
    };
    tick(); pairTimer = setInterval(tick, 1000);
  }

  function drawQr(box, text) {
    box.textContent = '';
    if (typeof qrcode !== 'function') return;
    const code = qrcode(0, 'M'); code.addData(text); code.make();
    const n = code.getModuleCount(), ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg'); svg.setAttribute('viewBox', '0 0 ' + n + ' ' + n); svg.setAttribute('shape-rendering', 'crispEdges');
    let d = '';
    for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (code.isDark(r, c)) d += 'M' + c + ' ' + r + 'h1v1h-1z';
    const path = document.createElementNS(ns, 'path'); path.setAttribute('d', d); path.setAttribute('fill', '#0d141c');
    svg.append(path); box.append(svg);
  }

  // ---- reading chat aloud ---------------------------------------------------------------------------------------------
  // The hub sends `say` to one window only, its "speaker": the chat window on the streaming PC (not one inside OBS, which
  // has no speakers of its own). Lines queue up and are read one at a time, never over each other.
  const synth = window.speechSynthesis, speaker = A.speech(30);
  let voices = [], blocked = null;
  const speakerRole = () => !ctx.remote && typeof window.obsstudio === 'undefined' && !!synth;
  function loadVoices() { voices = synth ? synth.getVoices() : []; fillVoices(); }
  if (synth) { synth.addEventListener('voiceschanged', loadVoices); loadVoices(); }
  const voicesReady = () => new Promise((resolve) => {                 // Chrome lists its voices a moment after the page opens
    if (!synth || voices.length) { resolve(); return; }
    const done = () => { loadVoices(); resolve(); };
    synth.addEventListener('voiceschanged', done, { once: true }); setTimeout(done, 3000);
  });

  function sayIt(item) { const now = speaker.add(item); if (now) talk(now); drawReading(); }

  async function talk(item) {
    drawReading();
    await voicesReady();
    if (speaker.current !== item) return;                              // stopped while the voices loaded
    // Exactly the saved voice; without it, a voice on this PC. Never an online one the streamer didn't pick.
    const voice = A.pickVoice(voices, item.voice, navigator.language);
    let over = false, timer = 0, alive = 0;
    const finish = () => {
      if (over) return; over = true; clearTimeout(timer); clearInterval(alive);
      const next = speaker.done(item); if (next) talk(next); else drawReading();
    };
    if (!voice) { note('Nothing read aloud: this browser has no voice on this PC to read with.', 'bad'); finish(); return; }
    const u = new SpeechSynthesisUtterance(A.clean(item.text));
    u.voice = voice; u.lang = voice.lang;
    u.rate = Math.min(2, Math.max(0.5, Number(item.rate) || 1));
    u.volume = Math.min(1, Math.max(0, item.volume == null ? 1 : Number(item.volume)));
    u.onend = finish;
    u.onerror = (e) => {
      if (e.error === 'not-allowed' && speaker.current === item) {     // the browser wants one click in this window first
        over = true; clearTimeout(timer); clearInterval(alive); blocked = item; drawNotice(); drawReading(); return;
      }
      finish();
    };
    timer = setTimeout(finish, [...u.text].length / (11 * u.rate) * 1000 + 8000);      // in case a voice never says it is done
    if (A.onlineVoice(voice)) alive = setInterval(() => { if (synth.speaking && !synth.paused) { synth.pause(); synth.resume(); } }, 10000);   // Chrome stops long online speech
    synth.speak(u);
  }

  function stopSpeech(tellHub) {
    const was = blocked; blocked = null;
    speaker.stop(); if (synth) synth.cancel();
    drawReading(); if (was) drawNotice();
    if (tellHub) api('/tts/skip', {});
  }
  const unblock = () => { if (!blocked) return; const item = blocked; blocked = null; drawNotice(); if (speaker.current === item) talk(item); };
  document.addEventListener('pointerdown', unblock, true);
  document.addEventListener('keydown', unblock, true);

  function drawReading() {
    const now = speaker.current;
    $('reading').hidden = !now;
    if (!now) return;
    $('reading-text').textContent = (blocked ? 'Waiting to read: ' : 'Reading: ') + A.clean(now.text);
    $('reading-more').textContent = speaker.waiting ? '+' + speaker.waiting + ' waiting' : '';
  }
  $('reading-stop').onclick = () => stopSpeech(true);

  async function readAloud(m) {
    const a = await api('/tts/say', { id: m.id });
    note(a.ok ? (ctx.remote ? 'Reading it aloud on the streaming PC.' : 'Reading it aloud.') : 'Not read aloud: ' + (a.why || 'no answer') + '.', a.ok ? 'good' : 'bad');
  }

  // ---- Settings → Text to speech ------------------------------------------------------------------------------------
  function fillVoices() {
    const sel = $('tts-voice'), groups = A.voiceGroups(voices, navigator.language);
    const want = tts.voice || (groups.local[0] && groups.local[0].name) || '';
    sel.textContent = '';
    [['On this PC', groups.local], ['Online (sends text to Microsoft/Google)', groups.online]].forEach(([label, list]) => {
      if (!list.length) return;
      const g = el('optgroup'); g.label = label;
      list.forEach((v) => g.append(new Option(v.name, v.name)));
      sel.append(g);
    });
    if (want && ![...groups.local, ...groups.online].some((v) => v.name === want)) sel.append(new Option(want + ' (not in this browser)', want));
    if (!sel.options.length) sel.append(new Option('No voices in this browser', ''));
    sel.value = want;
    showVoiceNote();
  }
  function showVoiceNote() {
    const v = voices.find((x) => x.name === $('tts-voice').value);
    $('tts-voice-note').hidden = !A.onlineVoice(v);
    $('tts-voice-note').textContent = A.onlineVoice(v) ? 'This voice sends the text it reads to ' + A.voiceMaker(v) + ' to make the audio.' : '';
  }

  function fillTts() {
    const s = tts;
    $('tts-enabled').checked = s.enabled; $('tts-read').value = s.read; $('tts-command').value = s.command;
    $('tts-names').checked = s.names; $('tts-links').checked = s.skip_links;
    $('tts-max').value = s.max_chars; $('tts-rate').value = s.rate; $('tts-volume').value = s.volume;
    document.querySelectorAll('[data-tts-p]').forEach((b) => { b.checked = s.platforms === 'all' || s.platforms.includes(b.dataset.ttsP); });
    fillVoices(); showTts();
  }
  function showTts() {
    $('tts-command-row').hidden = $('tts-read').value !== 'command';
    $('tts-max-out').textContent = $('tts-max').value + ' characters';
    $('tts-rate-out').textContent = Number($('tts-rate').value).toFixed(1) + '×';
    $('tts-volume-out').textContent = Math.round($('tts-volume').value * 100) + '%';
  }
  function readTts() {
    const ps = [...document.querySelectorAll('[data-tts-p]')].filter((b) => b.checked).map((b) => b.dataset.ttsP);
    return A.ttsSettings({ enabled: $('tts-enabled').checked, read: $('tts-read').value, command: $('tts-command').value, names: $('tts-names').checked,
                           skip_links: $('tts-links').checked, max_chars: $('tts-max').value, platforms: ps, voice: $('tts-voice').value,
                           rate: $('tts-rate').value, volume: $('tts-volume').value });
  }
  function drawTts() {
    const local = !ctx.remote;
    $('tts-form').hidden = !local;
    $('tts-remote').hidden = local;
    $('tts-remote').textContent = 'Reading aloud is set up on the streaming PC' + (tts.enabled ? ' and is on.' : '. It is off right now.');
    $('tts-test').hidden = !local || !synth;
    $('tts-saved').textContent = '';
    $('tts-where').hidden = !local;
    $('tts-where').textContent = !synth ? 'This browser can’t speak. Open the chat window in Chrome or Edge.'
      : speakerRole() ? 'This window reads aloud, on this PC’s speakers. Keep it open while you stream.'
      : 'The chat window in Chrome or Edge on this PC reads aloud (not the one inside OBS).';
    if (local && !$('tts-section').contains(document.activeElement)) fillTts();
  }
  let ttsSave = 0;
  $('tts-form').addEventListener('input', (e) => {
    if (e.target === $('tts-voice')) showVoiceNote();
    tts = readTts(); showTts();
    clearTimeout(ttsSave);
    ttsSave = setTimeout(async () => {
      const a = await api('/tts', { settings: tts });
      $('tts-saved').textContent = a.ok ? 'Saved.' : 'Not saved: ' + (a.why || 'no answer') + '.';
    }, 450);
  });
  $('tts-test').onclick = () => sayIt({ id: 'test-' + Date.now(), text: 'Hi chat! This is how CrossChat reads your messages.',
                                        voice: $('tts-voice').value, rate: $('tts-rate').value, volume: $('tts-volume').value });
  $('tts-stop').onclick = () => stopSpeech(true);

  // ---- Settings → Filters ---------------------------------------------------------------------------------------------
  function drawFilters() {
    [['words', 'filter-words', 'word'], ['users', 'filter-users', 'viewer']].forEach(([key, id, what]) => {
      const box = $(id); box.textContent = '';
      if (!filters[key].length) box.append(el('span', 'none', key === 'words' ? 'No words yet.' : 'No viewers yet.'));
      filters[key].forEach((text) => {
        const chip = el('span', 'fchip'), x = el('button', '', '✕'); x.type = 'button';
        x.setAttribute('aria-label', 'Remove ' + what + ' ' + text); x.title = 'Remove';
        x.onclick = () => saveFilters({ ...filters, [key]: filters[key].filter((t) => t !== text) });
        chip.append(el('span', '', text), x); box.append(chip);
      });
    });
    $('filter-commands').checked = filters.hide_commands;
    $('filter-bots').checked = filters.bots;
    $('filter-joins').checked = filters.joins;
    $('filter-count').textContent = filters.words.length + filters.users.length ? (filters.words.length + filters.users.length) + ' in use' : '';
  }
  async function saveFilters(next) {
    next = A.filterSettings(next);
    const a = await api('/filters', { settings: next });
    if (!a.ok) { note('Filters not saved: ' + (a.why || 'no answer') + '.', 'bad'); return false; }
    filters = next; drawFilters();
    return true;
  }
  function addFilter(key, input) {
    let text = A.clean($(input).value);
    if (key === 'users') text = text.replace(/^@/, '');
    if (!text) return;
    if (filters[key].length >= A.LIST_MAX) { note('Filters hold up to ' + A.LIST_MAX + ' of each.', 'bad'); return; }
    saveFilters({ ...filters, [key]: [...filters[key], text] }).then((ok) => { if (ok) { $(input).value = ''; $(input).focus(); } });
  }
  $('filter-word-add').onclick = () => addFilter('words', 'filter-word');
  $('filter-user-add').onclick = () => addFilter('users', 'filter-user');
  $('filter-word').onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); addFilter('words', 'filter-word'); } };
  $('filter-user').onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); addFilter('users', 'filter-user'); } };
  $('filter-commands').onchange = () => saveFilters({ ...filters, hide_commands: $('filter-commands').checked });
  $('filter-bots').onchange = () => saveFilters({ ...filters, bots: $('filter-bots').checked });
  $('filter-joins').onchange = () => saveFilters({ ...filters, joins: $('filter-joins').checked });

  async function filterUser(m, on) {
    const names = [m.name, m.handle].filter(Boolean).map((n) => n.toLowerCase());
    const users = on ? [...filters.users, m.handle || m.name] : filters.users.filter((u) => !names.includes(u.toLowerCase().replace(/^@/, '')));
    if (!(await saveFilters({ ...filters, users }))) return;
    if (on) { hideWho(m.handle || m.name, 'user'); note('Hiding ' + m.name + '’s messages here and on stream. Undo in Settings → Filters.', 'good'); }
    else note(m.name + '’s new messages show again.', 'good');
  }

  // ---- chat history (the streaming PC only): every stream's chat, saved by the hub ------------------------------------
  let logs = [], log = null;
  async function getJSON(path) {
    if (DEMO) return demoGet(path);
    const r = await fetch(path, { cache: 'no-store' });
    if (!r.ok) throw new Error(path + ': ' + r.status);
    return r.json();
  }
  const when = (t) => new Date(Number(t) || 0).toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });

  async function openHistory() {
    showLogList();
    if (!$('history').open) openDialog($('history'));
    const ul = $('logs'); ul.textContent = ''; ul.append(el('li', 'none', 'Loading…'));
    try { logs = (await getJSON('/logs')).logs || []; } catch (e) { logs = null; }
    drawLogs();
  }
  function showLogList() {
    log = null;
    $('history-title').textContent = 'Chat history';
    $('history-list').hidden = false; $('history-log').hidden = true; $('history-back').hidden = true;
  }
  function drawLogs() {
    const ul = $('logs'); ul.textContent = '';
    if (!logs) { ul.append(el('li', 'none', 'Could not load the chat history.')); return; }
    const good = logs.filter((g) => g && A.validLog(g.name));
    if (!good.length) ul.append(el('li', 'none', 'Nothing saved yet. Each stream’s chat is saved here while you’re live.'));
    good.forEach((g) => {
      const li = el('li'), b = el('button', 'log'); b.type = 'button';
      const n = Number(g.messages) || 0;
      b.append(el('b', '', when(g.started)),
               el('small', '', (g.ended ? A.span(g.ended - g.started) : 'live now') + ' · ' + n.toLocaleString() + (n === 1 ? ' message' : ' messages') + ' · ' + A.bytes(g.bytes)));
      b.onclick = () => openLog(g);
      li.append(b); ul.append(li);
    });
  }
  async function openLog(g) {
    $('history-list').hidden = true; $('history-log').hidden = false; $('history-back').hidden = false;
    $('history-title').textContent = when(g.started);
    [['csv', 'CSV'], ['html', 'HTML']].forEach(([ext]) => {
      const a = $('log-' + ext);
      a.href = '/logs/' + encodeURIComponent(g.name) + '.' + ext; a.download = 'crosschat-' + g.name + '.' + ext;
      a.onclick = DEMO ? (e) => { e.preventDefault(); note('Demo: there is no saved chat to export.'); } : null;
    });
    $('log-lines').textContent = ''; $('log-more').hidden = true; $('log-count').textContent = 'Loading…';
    let messages;
    try { messages = await getJSON('/logs/' + encodeURIComponent(g.name) + '.json'); } catch (e) { $('log-count').textContent = 'Could not load this stream’s chat.'; return; }
    log = { g, messages: Array.isArray(messages) ? messages : (messages && messages.messages) || [], hits: [], shown: 0 };
    filterLog();
    if (!touch.matches) $('log-search').focus();
  }
  function filterLog() {
    if (!log) return;
    log.hits = A.logFilter(log.messages, { text: $('log-search').value, p: $('log-p').value, questions: $('log-q').checked });
    log.shown = 0; $('log-lines').textContent = '';
    moreLog();
  }
  function moreLog() {
    const next = log.hits.slice(log.shown, log.shown + 300);
    next.forEach((m) => $('log-lines').append(logLine(m)));
    log.shown += next.length;
    const n = log.hits.length, all = log.messages.length;
    $('log-count').textContent = n.toLocaleString() + (n === 1 ? ' message' : ' messages') + (n !== all ? ' of ' + all.toLocaleString() : '');
    $('log-more').hidden = log.shown >= n;
  }
  // One saved line (chat history, viewer cards). dated: the day goes with the time (lines from earlier streams).
  function logLine(m, dated) {
    const li = el('li', 'line' + (m.kind === 'event' ? ' event' : '') + (m.hidden ? ' hid' : '') + (m.gone ? ' gone' : ''));
    const t = new Date(Number(m.t) || 0);
    const at = el('span', 'at', dated ? t.toLocaleDateString([], { month: 'short', day: 'numeric' }) : t.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }));
    if (dated) at.title = t.toLocaleString();
    li.append(at, tagFor(m.p));
    const body = el('span', 'said');
    if (m.kind === 'event') body.append(el('span', 'akind', A.alertWord(T.alertKind(m))), ' ', T.alertLine(m, null, A.name(m.p)));
    else {
      const who = el('b', 'name', m.name || ''); who.style.color = nameColor(m.color); body.append(who);
      body.append(m.text || '');
    }
    if (m.question) body.append(' ', el('span', 'flag q', 'Q'));
    if (m.hidden) body.append(' ', el('span', 'flag hid', 'hidden'));
    if (m.gone) body.append(' ', el('span', 'flag hid', 'deleted'));
    li.append(body);
    return li;
  }
  let logSearch = 0;
  $('log-search').addEventListener('input', () => { clearTimeout(logSearch); logSearch = setTimeout(filterLog, 150); });
  $('log-p').onchange = $('log-q').onchange = filterLog;
  $('log-more').onclick = moreLog;
  $('history-back').onclick = () => { showLogList(); drawLogs(); };
  $('history-open').onclick = () => { $('settings').close(); openHistory(); };

  // ---- viewer cards: one viewer's messages this stream and in earlier streams, and what can be done about them ---------
  let viewer = null, viewerSearch = 0;
  const clock = (t) => new Date(Number(t) || 0).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

  function openViewer(m) {
    viewer = { from: m, card: null };
    $('viewer-search').value = '';
    $('viewer-tag').replaceChildren(tagFor(m.p));
    $('viewer-title').textContent = m.name;
    $('viewer-where').textContent = 'on ' + A.name(m.p) + (m.handle ? ' · @' + m.handle : '');
    drawViewer(null, 'Loading…');
    if (!$('viewer').open) openDialog($('viewer'));
    loadViewer();
  }
  async function loadViewer() {
    const asked = viewer;
    let card = null;
    try { card = await getJSON(A.viewerPath(asked.from, $('viewer-search').value)); } catch (e) { card = null; }
    if (viewer !== asked) return;                 // another card was opened meanwhile
    asked.card = card && card.ok ? card : null;
    drawViewer(asked.card, asked.card ? '' : 'Could not load this viewer’s messages.');
  }
  function drawViewer(card, status) {
    const facts = $('viewer-facts'); facts.textContent = '';
    if (status) facts.append(el('li', 'none', status));
    A.viewerFacts(card, clock).forEach((f) => facts.append(el('li', '', f)));
    // Their newest message this stream is what "read aloud" and the moderation act on (else the one clicked).
    const latest = A.viewerLatest(card), m = latest ? { ...viewer.from, ...latest } : viewer.from;
    const menu = $('viewer-menu'), close = () => $('viewer').close();
    menu.textContent = '';
    const said = latest ? (m.hidden ? { ok: false, why: 'Hidden by your filters, so it is never read aloud' } : { ok: true })
      : { ok: false, why: card ? 'Nothing from them this stream' : '' };
    menu.append(item('🔊', 'Read aloud last message', said, () => readAloud(m), { hint: 'On the streaming PC’s speakers' }));
    menu.append(filterItem(m, close));
    group(menu, 'Moderate');
    modItems(menu, m, ctxNow(), close);
    const searched = !!A.clean($('viewer-search').value);
    [['viewer-stream', 'viewer-count', card && card.stream, false, searched ? 'Nothing this stream matches.' : 'No messages this stream yet.'],
     ['viewer-past', 'viewer-past-count', card && card.past, true, searched ? 'Nothing in earlier streams matches.' : 'Nothing in the chat history of earlier streams.']]
      .forEach(([id, count, rows, dated, none]) => {
        const ol = $(id); ol.textContent = '';
        (rows || []).forEach((r) => ol.append(logLine(r, dated)));
        if (card && !(rows || []).length) ol.append(el('li', 'none', none));
        $(count).textContent = rows && rows.length ? rows.length : '';
      });
    $('viewer-note').hidden = !(card && card.truncated);
    $('viewer-note').textContent = 'Showing the newest messages. Search to find older ones.';
  }
  $('viewer-search').addEventListener('input', () => { clearTimeout(viewerSearch); viewerSearch = setTimeout(loadViewer, 250); });

  // ---- Settings → Channels & options (this PC only): the parts of config.json worth changing, no hand-editing ---------
  let config = null;                              // what the hub has: { settings, restart, custom_window, first_run }
  const cfgId = (key) => 'cfg-' + key.replace(/\W/g, '-');

  async function loadConfig() {
    try { const c = await getJSON('/config/editable'); config = c && c.settings ? c : null; } catch (e) { config = null; }
    return config;
  }
  function drawChannels() {
    const box = $('channels-form');
    if ($('channels-section').contains(document.activeElement) && box.childElementCount) return;   // not under the cursor
    box.textContent = '';
    $('channels-save').disabled = !config;
    if (!config) { box.append(el('p', 'hint', 'Loading your settings…')); return; }
    let heading = '';
    A.CONFIG_FIELDS.forEach((f) => {
      if (f.group !== heading) { heading = f.group; box.append(el('h4', '', heading)); }
      const id = cfgId(f.key), value = config.settings[f.key], wrap = el('div', 'field');
      let input;
      if (f.type === 'bool') {
        const label = el('label', 'switch'); input = el('input'); input.type = 'checkbox'; input.checked = value === true;
        label.append(f.label, input); wrap.append(label);
      } else {
        const label = el('label', '', f.label); label.htmlFor = id;
        if (f.type === 'select') {
          input = el('select');
          f.options.forEach(([v, text]) => { const o = new Option(text, v); o.disabled = v === 'custom' && !config.custom_window; input.append(o); });
        } else {
          input = el('input'); input.type = 'text'; input.autocomplete = 'off'; input.spellcheck = false;
          if (f.type === 'int') { input.inputMode = 'numeric'; input.pattern = '[0-9]*'; input.className = 'num'; } else input.maxLength = f.max;
          if (f.placeholder) input.placeholder = f.placeholder;
        }
        input.value = value == null ? '' : String(value);
        wrap.append(label, input);
      }
      input.id = id;
      const hint = el('p', 'hint', f.hint + (config.restart.includes(f.key) ? ' Takes effect when OBS restarts.' : '')); hint.id = id + '-hint';
      input.setAttribute('aria-describedby', hint.id);
      wrap.append(hint); box.append(wrap);
    });
  }
  function readChannels() {
    const values = {}, problems = [];
    A.CONFIG_FIELDS.forEach((f) => {
      const input = $(cfgId(f.key)); if (!input) return;
      const r = A.configValue(f, f.type === 'bool' ? input.checked : input.value);
      if (r.why) problems.push({ f, why: r.why }); else values[f.key] = r.value;
    });
    return { values, problems };
  }
  function savedSay(text, tone) { $('channels-saved').textContent = text; $('channels-saved').className = 'saved' + (tone ? ' ' + tone : ''); }
  async function saveChannels() {
    if (!config) return;
    const { values, problems } = readChannels();
    if (problems.length) { savedSay(problems[0].why, 'bad'); $(cfgId(problems[0].f.key)).focus(); return; }
    const changes = A.configChanges(config.settings, values);
    if (!Object.keys(changes).length) { savedSay('Nothing changed.'); return; }
    $('channels-save').disabled = true; savedSay('Saving…');
    const a = await api('/config', { settings: changes });
    $('channels-save').disabled = false;
    if (!a.ok) { savedSay('Not saved: ' + (a.why || 'CrossChat did not answer.'), 'bad'); return; }
    savedSay(a.why || 'Saved.', a.restart_needed ? 'warn' : 'good');
    $('channels-first').hidden = true;
    if (document.activeElement && $('channels-section').contains(document.activeElement)) document.activeElement.blur();
    await loadConfig(); drawChannels();
  }
  $('channels-save').onclick = saveChannels;
  $('channels-form').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.tagName === 'INPUT') { e.preventDefault(); saveChannels(); } });

  // First run (no channel in config.json yet): Settings opens at Channels & options with a short prompt.
  async function openChannels(first) {
    drawSettings();
    $('channels-first').hidden = !first;
    if (!$('settings').open) openDialog($('settings'));
    $('channels-section').scrollIntoView({ block: 'start' });
    if (!config) { await loadConfig(); drawChannels(); }
    const input = $(cfgId('twitch')); if (input && first && !touch.matches) input.focus();
  }

  function drawSettings() {
    showTheme(); showDing(); drawTwitch(); drawKick(); drawRumble(); drawDiscord(); drawDevices(); drawTailscale(); drawHealth(); drawTts(); drawFilters();
    drawUpdate();
    $('channels-section').hidden = ctx.remote;
    $('channels-first').hidden = true; savedSay('');
    if (!ctx.remote) { drawChannels(); loadConfig().then(drawChannels); }
    $('devices-section').hidden = ctx.remote;
    $('firewall-hint').hidden = A.onMac(navigator.platform);       // (a Mac: the Pair button says what it needs)
    $('update-row').hidden = ctx.remote;
    $('filters-section').hidden = ctx.remote;
    $('history-section').hidden = ctx.remote;
    $('studio-row').hidden = ctx.remote;
    $('about').textContent = 'CrossChat ' + (ctx.version || '') + ' · ' + (ctx.remote ? 'this device: ' + (ctx.device || 'paired device')
      : 'the streaming PC' + (ctx.lanUrl ? ' · other devices reach it at ' + ctx.lanUrl : ''));
  }

  // ---- notices and the mode (this PC, or a paired device) -----------------------------------------------------------
  function drawNotice() {
    const n = $('notice'), text = n.querySelector('span');
    let say_ = '';
    if (ctx.unpaired) say_ = 'This device is no longer paired. Pair it again from Settings on the streaming PC.';
    else if (blocked) say_ = 'Click anywhere in this window once so it can read chat aloud (the browser asks for that).';
    else if (!ctx.remote && A.extensionBehind(document.documentElement.dataset.crosschat, ctx.version)) {
      say_ = 'The CrossChat extension in this browser is still ' + document.documentElement.dataset.crosschat + ' (CrossChat is ' + ctx.version
        + '). Open chrome://extensions (edge://extensions in Edge) and press the reload arrow on CrossChat, then reload this window (F5).';
    } else if (!DEMO && ctx.executorKnown && !ctx.executor) {
      say_ = ctx.remote ? 'Replies to YouTube and X need the CrossChat window open on the streaming PC (Chrome or Edge with the extension).'
        : ctx.bridge ? '' : 'Replies to YouTube and X go out through the CrossChat window in Chrome or Edge with the extension: '
          + A.openChatHow(navigator.platform) + '.';
      if (say_ && twitchAuth.state !== 'on' && ctx.states.twitch) say_ += ' Connect Twitch in Settings' + (ctx.remote ? ' on the streaming PC' : '') + ' to reply on Twitch.';
    }
    n.hidden = !say_;
    text.textContent = say_;
  }

  function applyMode() {
    $('device').hidden = !ctx.remote;
    $('device').querySelector('span').textContent = ctx.device || 'Paired device';
    $('studio').hidden = ctx.remote;
    document.title = 'CrossChat · chat' + (ctx.remote ? ' (' + (ctx.device || 'companion') + ')' : '');
    drawNotice();
  }

  function connected(on) {
    $('lost').style.display = on ? 'none' : 'inline';
    $('device').querySelector('.dot').className = 'dot' + (on ? ' ok' : '');
  }

  function unpaired() { ctx.unpaired = true; drawNotice(); if (feed) feed.close(); }

  // ---- the live feed ------------------------------------------------------------------------------------------------
  function handle(m) {
    switch (m.type) {
      case 'msg': add(m); break;
      case 'status': {
        ctx.states = m.status || {}; health = m.health || {}; drawPlatforms(); youtubeBox(m.yt || ''); refreshActs();
        if ($('settings').open) drawHealth();
        const live = $('live'); live.className = m.live ? 'on' : ''; live.textContent = m.live ? 'LIVE' : 'OFF AIR';
        break;
      }
      case 'viewers': counts = m.counts || {}; drawPlatforms(); $('total').firstChild.textContent = m.total; break;
      case 'delete': { const row = rowOf(m.id); if (row) row.classList.add('gone'); break; }
      case 'purge': list.querySelectorAll('[data-who="' + CSS.escape(m.p + ':' + m.name) + '"]').forEach((row) => row.classList.add('gone')); break;
      case 'clear': list.querySelectorAll('.m').forEach((n) => n.remove()); msgs.clear(); setReply(null); drawViews(); break;
      case 'feature': showFeatured(m.msg); break;
      case 'outbox': if (m.job && executorRole()) runJob(m.job); break;
      case 'sent': finish(m.job_id, m.answer); break;
      case 'starred': starred = new Set(m.ids || []); drawStars(); break;
      case 'quick': quick = A.cleanQuick(m.replies); drawQuick(); break;
      case 'executor': ctx.executor = !!m.present; ctx.executorKnown = true; drawNotice(); drawPlatforms(); refreshActs(); break;
      case 'twitch_auth': twitchAuth = m; drawTwitch(); drawNotice(); refreshActs(); break;
      case 'rumble_auth': rumbleAuth = m; drawRumble(); break;
      case 'discord_auth': discordAuth = m; drawDiscord(); break;
      case 'companion': companion = m; drawTailscale(); break;
      case 'update': update = m; drawUpdate(); break;
      case 'kick_auth':
        kickAuth = m;
        if (m.state === 'pending' && kickWanted && !ctx.remote) openKick(m.url);
        else if (m.state !== 'pending') kickWanted = false;
        drawKick(); drawPlatforms(); refreshActs();
        break;
      case 'devices': devices = m.devices || []; drawDevices(); break;
      case 'pair': showPair(m); break;
      case 'emotes': emotes = F.emoteMap(m.emotes); rewords(); break;
      case 'say': if (speakerRole() || DEMO) sayIt({ id: m.id, text: m.text, voice: m.voice, rate: m.rate, volume: m.volume }); break;
      case 'say_stop': stopSpeech(false); break;
      case 'tts': tts = A.ttsSettings(m.settings); if ($('settings').open) drawTts(); break;
      case 'filters': filters = A.filterSettings(m.settings); if ($('settings').open && !$('filters-section').contains(document.activeElement)) drawFilters(); break;
      case 'config': if (m.settings) { config = { settings: m.settings, restart: m.restart || [], custom_window: !!m.custom_window, first_run: !!m.first_run }; if ($('settings').open) drawChannels(); } break;
      case 'hide':                                // the hub hid messages after the fact: { id } or { p, name }, with why
        if (m.id) { const msg = msgs.get(m.id); if (msg) { msg.hidden = m.why || 'user'; const row = rowOf(m.id); if (row) hideRow(row, msg.hidden); } }
        else hideWho(m.name, m.why || 'user', m.p);
        break;
      default: break;                             // theme and anything newer: not for this page
    }
  }

  const executorRole = () => !ctx.remote && ctx.bridge;

  function youtubeBox(video) {                    // the executor keeps YouTube's own chat box at hand for replies
    let frame = $('yt');
    if (frame && frame.dataset.v === video) return;
    if (frame) frame.remove();
    if (!video || !executorRole() || DEMO) return;
    frame = el('iframe'); frame.id = 'yt'; frame.dataset.v = video; frame.tabIndex = -1; frame.title = 'YouTube chat (used to send replies)';
    frame.setAttribute('aria-hidden', 'true');
    frame.src = 'https://www.youtube.com/live_chat?v=' + encodeURIComponent(video) + '&embed_domain=' + location.hostname;
    document.body.append(frame);
  }

  function connect() {
    const roles = [executorRole() && 'executor=1', speakerRole() && 'speaker=1'].filter(Boolean);
    feed = new EventSource('/events' + (roles.length ? '?' + roles.join('&') : ''));
    feed.onopen = () => { connected(true); list.querySelectorAll('.m').forEach((n) => n.remove()); msgs.clear(); setReply(null); drawViews(); };
    feed.onerror = () => {
      connected(false);
      if (ctx.remote) fetch('/whoami', { cache: 'no-store' }).then((r) => { if (r.status === 401 || r.status === 403) unpaired(); }).catch(() => {});
    };
    feed.onmessage = (e) => { try { handle(JSON.parse(e.data)); } catch (err) { /* a line this page does not understand */ } };
  }

  async function start() {
    showDing(); showTheme(); drawQuick(); drawViews();
    if (touch.matches) say.placeholder = 'Message every live chat';
    if (DRY) say.placeholder = 'TEST MODE: nothing typed here is posted.';
    if (DEMO) { demo(); return; }
    try {
      const r = await fetch('/whoami', { cache: 'no-store' });
      if (r.status === 401 || r.status === 403) { ctx.remote = true; unpaired(); applyMode(); return; }
      const w = await r.json();
      Object.assign(ctx, { remote: !!w.remote, device: w.device || null, version: w.version || '', lanUrl: w.lan_url || null });
    } catch (e) { /* an older hub: behave as the window on this PC */ }
    applyMode();
    connect();
    drawEntry();
    if (!ctx.remote && (await loadConfig()) && config.first_run) openChannels(true);
  }

  // ---- ?demo: made-up people and lines, no network ------------------------------------------------------------------
  function demoApi(path, body) {
    const ok = (extra) => Promise.resolve(Object.assign({ ok: true }, extra || {}));
    const id = 'demo-job-' + Math.random().toString(36).slice(2);
    if (path === '/send') {
      setTimeout(() => {
        body.to.forEach((p) => handle({ type: 'msg', id: 'demo-you-' + p + Date.now(), t: Date.now(), p, name: 'you', badges: ['broadcaster'], color: '#e3a57b', kind: 'chat', text: body.text }));
        handle({ type: 'sent', job_id: id, answer: Object.fromEntries(body.to.map((p) => [p, { ok: true }])) });
      }, 350);
      return ok({ job_id: id });
    }
    if (path === '/mod') {
      setTimeout(() => {
        if (body.action !== 'unban') handle({ type: body.action === 'delete' ? 'delete' : 'purge', id: [...msgs.values()].find((m) => m.mid === body.message_id)?.id, p: body.p, name: (body.name || '').toLowerCase() });
        handle({ type: 'sent', job_id: id, answer: { ok: true } });
      }, 350);
      return ok({ job_id: id });
    }
    if (path === '/feature') { handle({ type: 'feature', msg: body.id ? msgs.get(body.id) : null }); return ok(); }
    if (path === '/star') { const s = new Set(starred); if (body.on) s.add(body.id); else s.delete(body.id); handle({ type: 'starred', ids: [...s] }); return ok(); }
    if (path === '/quick') { handle({ type: 'quick', replies: body.replies }); return ok(); }
    if (path === '/pair/start') { handle({ type: 'pair', code: '482913', url: 'http://192.168.1.20:4467/pair?code=482913', expires: Date.now() / 1000 + 300 }); return ok(); }
    if (path === '/twitch/connect') { handle({ type: 'twitch_auth', state: 'pending', user_code: 'WDJB-MJHT', verification_uri: 'https://www.twitch.tv/activate' }); return ok(); }
    if (path === '/twitch/disconnect') { handle({ type: 'twitch_auth', state: 'off' }); return ok(); }
    if (path === '/devices/revoke') { handle({ type: 'devices', devices: devices.filter((d) => d.id !== body.id) }); return ok(); }
    if (path === '/kick/connect') { handle({ type: 'kick_auth', state: 'pending' }); setTimeout(() => handle({ type: 'kick_auth', state: 'on', login: 'you' }), 1500); return ok(); }
    if (path === '/kick/disconnect') { handle({ type: 'kick_auth', state: 'off' }); return ok(); }
    if (path === '/rumble/connect') { handle({ type: 'rumble_auth', state: 'on' }); return ok(); }
    if (path === '/rumble/disconnect') { handle({ type: 'rumble_auth', state: 'off' }); return ok(); }
    if (path === '/config') {                     // as the hub answers: saved, and which changes wait for OBS to restart
      const changes = body.settings || {}, later = Object.keys(changes).filter((k) => demoConfig.restart.includes(k));
      Object.assign(demoConfig.settings, changes);
      const label = (k) => (A.CONFIG_FIELDS.find((f) => f.key === k) || { label: k }).label;
      return ok({ why: later.length ? 'Saved. Restart OBS to apply: ' + later.map(label).join(', ') + '.' : 'Saved.', restart_needed: !!later.length, restart: later });
    }
    if (path === '/discord/connect') { handle({ type: 'discord_auth', state: 'on', name: 'stream-chat', live: true, featured: true, chat: false }); return ok(); }
    if (path === '/discord/options') { handle(Object.assign({}, discordAuth, body, { type: 'discord_auth' })); return ok(); }
    if (path === '/discord/disconnect') { handle({ type: 'discord_auth', state: 'off' }); return ok(); }
    if (path === '/companion/tailscale') { handle({ type: 'companion', tailscale: !!body.on, address: body.on ? '100.101.102.103' : '', listening: false, why: '' }); return ok(); }
    if (path === '/updates') { handle({ type: 'update', check: !!body.check, version: '', url: '' }); return ok(); }
    if (path === '/tts') { setTimeout(() => handle({ type: 'tts', settings: body.settings }), 50); return ok(); }
    if (path === '/filters') { setTimeout(() => handle({ type: 'filters', settings: body.settings }), 50); return ok(); }
    if (path === '/tts/skip') { handle({ type: 'say_stop' }); return ok(); }
    if (path === '/tts/say') {
      const m = msgs.get(body.id);
      if (m) handle({ type: 'say', id: m.id, text: (tts.names ? m.name + ' says: ' : '') + m.text, voice: tts.voice, rate: tts.rate, volume: tts.volume });
      return ok();
    }
    return ok();
  }

  // ?demo settings: placeholder channels, nothing real.
  const demoConfig = {
    settings: { twitch: 'your_channel', youtube: '@yourchannel', kick: 'your_channel', tiktok: '', facebook: false, 'x.enabled': true, 'x.auto_go_live': false,
                'x.title': 'Building a chat app live', 'x.title_file': '', 'x.source': 'OBS', window: 'auto', open_window_on_stream_start: true,
                close_window_seconds_after_stream: 120, 'emotes.bttv': true, 'emotes.ffz': true, 'emotes.7tv': true, 'logs.enabled': true, 'logs.keep_days': 90,
                'remote.enabled': true, 'remote.port': 4467 },
    restart: ['twitch', 'youtube', 'kick', 'tiktok', 'facebook', 'x.enabled'], custom_window: false, first_run: false,
  };
  if (DEMO_KIND === 'firstrun') {
    Object.assign(demoConfig.settings, { twitch: '', youtube: '', kick: '', 'x.enabled': false, 'x.title': 'Live now' });
    demoConfig.first_run = true;
  }

  // ?demo viewer card: the viewer's lines in this page, and made-up ones from two earlier streams.
  function demoViewer(path) {
    const q = new URLSearchParams(path.split('?')[1] || ''), p = q.get('p'), who = String(q.get('name') || '').toLowerCase();
    const search = String(q.get('q') || '').toLowerCase(), hit = (m) => !search || String(m.text || '').toLowerCase().includes(search);
    const mine = [...msgs.values()].filter((m) => m.p === p && m.kind !== 'note' && String(m.name || '').toLowerCase() === who);
    const chat = mine.filter((m) => m.kind === 'chat'), day = 24 * 3600000, first = chat.some((m) => m.first === 'ever');
    const past = first ? [] : ['that build from last week still runs great', 'is the overlay open source?', 'gg, see you Thursday', 'how do you keep chat this fast?']
      .map((text, i) => ({ id: 'old-' + i, t: Date.now() - (i < 2 ? 2 : 5) * day - i * 600000, p, name: mine[0] ? mine[0].name : who, kind: 'chat', text,
                           stream: i < 2 ? 'demo-tuesday' : 'demo-saturday' })).filter(hit);
    return Promise.resolve({ ok: true, p, name: mine[0] ? mine[0].name : who, count: chat.length, first_seen: chat.length ? chat[0].t : null,
                             first_ever: first, history: true, stream: mine.filter(hit).reverse(), past, past_streams: first ? 0 : 2, truncated: false });
  }

  // ?demo chat history: three streams of made-up chat.
  function demoGet(path) {
    if (path === '/config/editable') return Promise.resolve(JSON.parse(JSON.stringify(demoConfig)));
    if (path.startsWith('/viewer?')) return demoViewer(path);
    const hour = 3600000, start = new Date(); start.setHours(13, 45, 0, 0);
    const day = (n) => start.getTime() - n * 24 * hour;
    const all = [
      { name: 'demo-today', started: day(0), ended: null, messages: 1284, bytes: 221184 },
      { name: 'demo-tuesday', started: day(2) + 2 * hour, ended: day(2) + 4.2 * hour, messages: 3910, bytes: 702464 },
      { name: 'demo-saturday', started: day(5) - hour, ended: day(5) + 1.5 * hour, messages: 2207, bytes: 391168 },
    ];
    if (path === '/logs') return Promise.resolve({ logs: all });
    const from = (all.find((g) => path === '/logs/' + g.name + '.json') || all[0]).started;
    const who = [['twitch', 'pixel_pirate', '#ff7f50'], ['youtube', 'Maya Chen', ''], ['x', 'Dev Daily', ''], ['kick', 'turbo_kat', '#53fc18'],
                 ['twitch', 'nightowl_42', '#1e90ff'], ['youtube', 'Sam Ortiz', ''], ['twitch', 'kiwi_codes', '#9acd32'], ['youtube', 'Rafael Gomes', ''],
                 ['tiktok', 'luna.makes', '']];
    const said = ['what are we building today?', 'hello from Lisbon 👋', 'one chat for every platform, finally', 'W stream', 'welcome in everyone',
                  'can you show how replies reach every platform?', 'that boss fight was wild', 'what keyboard is that?', 'how do I set up the overlay?',
                  'gg', 'is the theme studio free too?', 'love the new layout'];
    return Promise.resolve(Array.from({ length: 160 }, (_, i) => {
      const [p, name, color] = who[(i * 5) % who.length], text = said[(i * 7) % said.length];
      return { id: 'log-' + i, t: from + i * 41000, p, name, color, kind: 'chat', text, question: /\?$/.test(text) };
    }));
  }

  function demo() {
    const remote = DEMO_KIND === 'remote';
    Object.assign(ctx, { remote, device: remote ? 'Phone' : null, version: '1.4.0', lanUrl: 'http://192.168.1.20:4467/', executor: true, executorKnown: true });
    applyMode(); connected(true);
    const t = Date.now() - 9 * 60000, at = (min) => t + min * 60000, ago = (s) => Date.now() - s * 1000;
    handle({ type: 'status', live: true, status: { twitch: 'on', youtube: 'on', kick: 'on', x: 'on', tiktok: 'on' },
             health: { twitch: { since: ago(4320), last: ago(8), reconnects: 0 }, youtube: { since: ago(4290), last: ago(3), reconnects: 2 },
                       kick: { since: ago(1260), last: ago(41), reconnects: 1 }, x: { since: ago(4250), last: ago(95), reconnects: 0 },
                       tiktok: { since: ago(4200), last: ago(12), reconnects: 0 } } });
    handle({ type: 'viewers', counts: { twitch: 128, youtube: 342, kick: 41, x: 87, tiktok: 214 }, total: 812 });
    handle({ type: 'twitch_auth', state: 'on', login: 'you' });
    handle({ type: 'kick_auth', state: 'on', login: 'you' });
    handle({ type: 'tts', settings: { enabled: true, read: 'questions', names: true, max_chars: 200, skip_links: true, platforms: 'all', voice: '', rate: 1.1, volume: 0.8 } });
    handle({ type: 'filters', settings: { words: ['spoiler', 'cheap followers', 'dm me'], users: ['bot_4417'], hide_commands: true, bots: true } });
    handle({ type: 'quick', replies: ['Welcome in! 👋', 'Thanks for the follow!', 'GG', 'Be right back', 'Links are in the panels below', '❤'] });
    handle({ type: 'devices', devices: [{ id: 'd1', name: 'Phone', created: at(-3000) / 1000, last_seen: Date.now() / 1000 },
                                          { id: 'd2', name: 'Laptop', created: at(-9000) / 1000, last_seen: at(-1500) / 1000 }] });
    [{ kind: 'note', p: 'system', text: 'Stream started. Chat from every platform shows up here.', t: at(0) },
     { p: 'twitch', name: 'pixel_pirate', color: '#ff7f50', text: 'first! what are we building today?', question: true, first: 'ever', t: at(1), mid: 'a1', uid: '101' },
     { p: 'youtube', name: 'Maya Chen', badges: ['member'], text: 'Watching from Lisbon 👋 love the new overlay', t: at(1.5), mid: 'y1' },
     { p: 'x', name: 'Dev Daily', handle: 'devdaily', text: 'One chat for every platform, finally', t: at(2) },
     { p: 'kick', name: 'turbo_kat', color: '#53fc18', text: 'W stream, audio sounds great', t: at(3) },
     { p: 'twitch', kind: 'event', name: 'nightowl_42', alert: 'resub', amount: '6', system: 'nightowl_42 subscribed for 6 months!', text: 'half a year already', t: at(4) },
     { p: 'twitch', name: 'nightowl_42', color: '#1e90ff', badges: ['moderator'], text: 'welcome in, new folks 🙂', t: at(4.5), mid: 'a2', uid: '102' },
     { p: 'youtube', name: 'Sam Ortiz', text: 'can you show how replies reach every platform?', question: true, t: at(6), id: 'yt-sam', mid: 'y2' },
     { p: 'twitch', name: 'bot_4417', color: '#7fff00', text: 'cheap followers!!! dm me for a deal', t: at(6.5), id: 'tw-spam', mid: 'a3', uid: '103',
       hidden: DEMO_KIND === 'mod' ? undefined : 'user' },
     { p: 'kick', name: 'quietstorm', color: '#f4a261', text: 'hey all, first time catching you live', first: 'ever', t: at(6.8), mid: 'k2' },
     { p: 'x', name: 'Lena Park', handle: 'lenapark', text: 'does the overlay work with Streamlabs too?', question: true, t: at(7) },
     { p: 'tiktok', name: 'luna.makes', text: 'found you on TikTok, this setup is so clean', first: 'stream', t: at(7.2) },
     { p: 'youtube', name: 'Rafael Gomes', text: 'what keyboard is that?', question: true, t: at(7.5), id: 'yt-kb', mid: 'y3' }]
      .forEach((m, i) => handle({ type: 'msg', id: m.id || 'demo-' + i, kind: 'chat', color: '', badges: [], ...m }));
    echoes.push({ text: 'Thanks all! Typing once here answers Twitch, YouTube and X together', to: ['twitch', 'youtube', 'x'], t: Date.now() });
    ['twitch', 'youtube', 'x'].forEach((p) => handle({ type: 'msg', id: 'demo-mine-' + p, p, kind: 'chat', name: 'you', badges: ['broadcaster'], color: '#e3a57b', t: at(8),
      text: 'Thanks all! Typing once here answers Twitch, YouTube and X together' }));
    handle({ type: 'starred', ids: ['yt-kb', 'demo-1'] });
    if (DEMO_KIND === 'reply') {
      setReply(msgs.get('yt-sam')); say.value = '@Sam Ortiz sure! tap a message, press reply, and it goes back to YouTube only'; drawEntry();
      showFeatured(msgs.get('yt-sam'));
    }
    if (DEMO_KIND === 'mod') {
      openSheet(msgs.get('tw-spam'));
      const label = [...document.querySelectorAll('#sheet-menu .label')].find((l) => l.textContent === 'Moderate');
      if (label) label.scrollIntoView({ block: 'start' });
    }
    const SECTION = { tts: 'tts-section', filters: 'filters-section', health: 'connections-section' };
    if (DEMO_KIND === 'settings' || DEMO_KIND === 'pair' || SECTION[DEMO_KIND]) { drawSettings(); openDialog($('settings')); }
    if (DEMO_KIND === 'pair') { api('/pair/start', {}); $('pair').scrollIntoView({ block: 'center' }); }
    if (SECTION[DEMO_KIND]) $(SECTION[DEMO_KIND]).scrollIntoView({ block: 'start' });
    if (DEMO_KIND === 'tts') {                    // what the speaker window shows while it reads (nothing is spoken)
      speaker.add({ id: 'demo-say', text: 'Rafael Gomes says: what keyboard is that?' }); speaker.add({ id: 'demo-say-2', text: 'Sam Ortiz says: can you show how replies reach every platform?' });
      drawReading();
    }
    if (DEMO_KIND === 'history') openHistory().then(() => openLog(logs[1]));
    if (DEMO_KIND === 'quick') openQuickEditor();
    if (DEMO_KIND === 'channels' || DEMO_KIND === 'firstrun') openChannels(DEMO_KIND === 'firstrun');
    if (DEMO_KIND === 'viewer') openViewer(msgs.get('demo-6'));
    if (DEMO_KIND === 'alerts') {                 // every platform's alerts, as they arrive from the hub
      [{ p: 'youtube', name: 'Maya Chen', alert: 'superchat', amount: '$10.00', system: 'Super Chat $10.00', text: 'Thanks for the tutorial, it finally clicked!' },
       { p: 'youtube', name: 'Priya N', alert: 'superchat', amount: '$2.00', system: 'Super Sticker $2.00' },
       { p: 'youtube', name: 'Rafael Gomes', alert: 'gift', amount: '5 memberships', system: 'Rafael Gomes gifted 5 memberships' },
       { p: 'youtube', name: 'Sam Ortiz', alert: 'member', system: 'Welcome to Members!' },
       { p: 'twitch', name: 'bitbucket', alert: 'cheer', amount: '500 bits', system: 'bitbucket cheered 500 bits', text: 'Cheer500 great stream' },
       { p: 'twitch', name: 'raid_leader', alert: 'raid', amount: '37', system: '37 raiders from raid_leader have joined!' },
       { p: 'twitch', name: 'kiwi_codes', alert: 'resub', amount: '', system: 'kiwi_codes subscribed at Tier 1.' },
       { p: 'kick', name: 'turbo_kat', alert: 'gift', amount: '3 subs', system: 'turbo_kat gifted 3 subs' },
       { p: 'kick', name: 'glitchfox', alert: 'raid', amount: '12', system: 'glitchfox is raiding with 12 viewers' },
       { p: 'rumble', name: 'trailhead_tv', alert: 'superchat', amount: '$5.00', system: 'trailhead_tv sent a $5.00 Rant', text: 'Keep the builds coming' },
       { p: 'rumble', name: 'maple_moto', alert: 'gift', amount: '2 subs', system: 'maple_moto gifted 2 subs' },
       { p: 'twitch', name: 'AriaPlays', alert: 'announcement', system: 'AriaPlays shared an announcement', text: 'Giveaway at the top of the hour!' }]
        .forEach((e, i) => handle({ type: 'msg', id: 'demo-alert-' + i, kind: 'event', color: '', badges: [], text: '', t: at(8.2 + i * 0.05), ...e }));
    }
  }

  start();
})(globalThis.CrossChatApp);
