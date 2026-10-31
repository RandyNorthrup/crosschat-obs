// The four on-stream widgets: chat feed, featured message, viewer counter and alerts. overlay.html loads this and
// the address picks the widget (/overlay/chat, /overlay/featured, /overlay/viewers, /overlay/alerts).
// Data comes from the hub's /events feed; ?demo shows made-up data instead (?demo=still holds it still, for
// screenshots); ?preview is the Theme Studio's copy, which takes its theme from the Studio rather than the hub.
// Everything viewers typed goes onto the page as text only (textContent), never as HTML. Messages the streamer's
// filters hide (m.hidden) never show here.
(() => {
  const T = window.CrossChatTheme, I = window.CrossChatIcons, F = window.CrossChatFeed, doc = document;
  const q = new URLSearchParams(location.search);
  const WIDGET = (/\/overlay\/(chat|featured|viewers|alerts)\b/.exec(location.pathname) || [])[1] || q.get('widget') || 'chat';
  const PREVIEW = q.has('preview'), DEMO = PREVIEW || q.has('demo'), STILL = q.get('demo') === 'still';
  const SHORT = { twitch: 'TW', youtube: 'YT', kick: 'K', x: 'X' };
  const BADGES = { broadcaster: 'host', owner: 'host', moderator: 'mod', vip: 'vip', subscriber: 'sub', founder: 'sub', member: 'member', verified: '✓' };
  const root = doc.getElementById('cc-root');
  doc.documentElement.dataset.widget = WIDGET;
  if (STILL) doc.documentElement.dataset.still = '';

  let theme = T.merge({}), shown = 'all', live = false, primed = false, emotes = new Map();
  let themed = false, early = [];                  // chat that came before the theme (and so its delay) was known

  // ---- theme ----------------------------------------------------------------------------------------
  // Address overrides, for one OBS source that differs a little from its theme (documented in docs/THEMES.md).
  function overrides() {
    const o = {}, put = (path, v) => { const keys = path.split('.'); let at = o; keys.slice(0, -1).forEach((k) => { at = at[k] = at[k] || {}; }); at[keys[keys.length - 1]] = v; };
    const MAP = { size: 'font.size', layout: 'message.layout', icons: 'message.platform', max: 'chat.max', seconds: 'chat.seconds', direction: 'chat.direction',
                  align: 'chat.align', scale: 'featured.scale', volume: 'alerts.volume', opacity: 'colors.backgroundOpacity', delay: 'chat.delay' };
    Object.entries(MAP).forEach(([k, path]) => { if (q.has(k)) put(path, q.get(k)); });
    if (q.has('sound')) put('alerts.sound', !/^(0|off|false|no)$/i.test(q.get('sound')));
    if (q.has('badges')) put('message.badges', !/^(0|off|false|no)$/i.test(q.get('badges')));
    return o;
  }

  function useTheme(raw) {
    theme = T.merge(raw || {}, overrides());
    T.apply(theme, doc);
    shown = T.wanted(theme.chat.platforms, q.get('platforms'));
    redraw();
    themed = true;
    const waiting = early; early = [];
    waiting.forEach((e) => chatIn(e.m, e.live, e.at));
  }

  const getJSON = (path) => fetch(path, { cache: 'no-store' }).then((r) => { if (!r.ok) throw new Error(path + ': ' + r.status); return r.json(); });

  async function loadTheme() {
    if (PREVIEW) return;
    try {
      const name = q.get('theme') || (await getJSON('/themes')).default || 'classic';
      useTheme(await getJSON('/themes/' + encodeURIComponent(name)));
    } catch (e) {
      useTheme({});                                // no hub (or no such theme): the built-in look
    }
  }

  // ---- drawing one message ----------------------------------------------------------------------------
  function platformMark(p) {
    if (theme.message.platform === 'text') {
      const tag = doc.createElement('span'); tag.className = 'cc-tag'; tag.textContent = SHORT[p] || '•'; return tag;
    }
    const icon = doc.createElement('span'); icon.className = 'cc-icon'; icon.appendChild(I.icon(p, doc)); return icon;
  }

  function colourFor(el, m) {
    const own = theme.colors[m.p] || theme.colors.accent;
    el.style.setProperty('--cc-p', own);
    el.style.setProperty('--cc-ink', T.ink(own));
    el.style.setProperty('--cc-name', T.nameColor(m, theme));
  }

  function words(into, m) {                        // Twitch's own emotes first, then 7TV / BetterTTV / FrankerFaceZ words
    const surface = T.lightSurface(theme) ? 'light' : 'dark';
    F.withEmotes(T.emotePieces(m.text, m.p === 'twitch' ? m.emotes : ''), emotes).forEach((piece) => {
      if (piece.text !== undefined) { into.appendChild(doc.createTextNode(piece.text)); return; }
      const img = doc.createElement('img');
      img.className = 'cc-emote'; img.alt = piece.alt; img.decoding = 'async';
      img.src = piece.url || 'https://static-cdn.jtvnw.net/emoticons/v2/' + piece.emote + '/default/' + surface + '/2.0';
      into.appendChild(img);
    });
  }

  // A sub, raid, cheer or Super Chat as one line in the chat feed: the theme's alert sentence ("{name} cheered {amount}!"),
  // or the platform's own sentence, then whatever the viewer wrote.
  function eventLine(m) {
    const template = m.alert && theme.alerts.labels[m.alert];
    const values = { name: m.name || '', amount: m.amount || '', text: m.text || '', platform: I.NAMES[m.p] || '' };
    let line = template ? template.replace(/\{(name|amount|text|platform)\}/g, (_, k) => values[k]).replace(/\s+/g, ' ').trim() : (m.system || '');
    if (m.text && !(template && template.includes('{text}')) && m.text !== line) line = (line ? line + ' · ' : '') + m.text;
    return line || m.system || m.text || '';
  }

  function message(m, cls) {
    const el = doc.createElement('div');
    el.className = cls; el.dataset.platform = m.p; el.dataset.kind = m.kind || 'chat'; el.dataset.id = m.id;
    if (m.first === 'ever' || m.first === 'stream') el.dataset.first = m.first;
    colourFor(el, m);
    const head = doc.createElement('span'); head.className = 'cc-head';
    if (m.first === 'ever' && m.kind !== 'event' && theme.message.firstHighlight) {   // a first-time chatter
      el.classList.add('cc-first');
      const tag = doc.createElement('span'); tag.className = 'cc-first-tag'; tag.textContent = 'NEW'; head.appendChild(tag);
    }
    (m.badges || []).map((b) => BADGES[b]).filter((b, i, all) => b && all.indexOf(b) === i).forEach((b) => {
      const badge = doc.createElement('span'); badge.className = 'cc-badge'; badge.textContent = b; head.appendChild(badge);
    });
    const name = doc.createElement('span'); name.className = 'cc-name'; name.textContent = m.name || ''; head.appendChild(name);
    if (cls === 'cc-featured' && theme.featured.platform && I.NAMES[m.p]) {
      const where = doc.createElement('span'); where.className = 'cc-where'; where.textContent = 'on ' + I.NAMES[m.p]; head.appendChild(where);
    }
    const time = doc.createElement('span'); time.className = 'cc-time';
    time.textContent = new Date(m.t || Date.now()).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    const text = doc.createElement('span'); text.className = 'cc-text';
    if (m.kind === 'event' && cls !== 'cc-featured') text.textContent = eventLine(m);
    else words(text, m);
    if (cls === 'cc-featured') {                   // featured: a small header line (platform, name), the text big below it
      head.prepend(platformMark(m.p));
      head.appendChild(time);
      el.append(head, text);
      return el;
    }
    const main = doc.createElement('div'); main.className = 'cc-main';
    main.append(head, text, time);
    el.append(platformMark(m.p), main);
    return el;
  }

  function leave(el, then) {
    if (!el) { if (then) then(); return; }
    if (el.classList.contains('cc-out')) return;
    const none = WIDGET === 'chat' && theme.chat.animationOut === 'none';
    if (none) { el.remove(); if (then) then(); return; }
    el.classList.remove('cc-new'); el.classList.add('cc-out');
    setTimeout(() => { el.remove(); if (then) then(); }, 620);
  }

  // ---- chat feed ------------------------------------------------------------------------------------------
  const chat = { items: [], seen: new Set() };

  function chatShows(m) {
    if (m.kind === 'note' || m.p === 'system') return false;
    if (m.kind === 'event' && !theme.chat.events) return false;
    return T.shows(shown, m.p);
  }

  // born: when the message counts as arrived (a held message's time on screen starts when it shows).
  function chatAdd(m, animate, born) {
    if (chat.seen.has(m.id) || m.hidden) return;
    chat.seen.add(m.id);
    if (chat.seen.size > 2000) chat.seen.delete(chat.seen.values().next().value);
    born = born || m.t || Date.now();
    const life = theme.chat.seconds * 1000;
    if (life && Date.now() - born >= life) return;
    const item = { m, el: null, timer: 0, born };
    chat.items.push(item);
    draw(item, animate);
    trim();
  }

  // The display delay (theme chat.delay, or ?delay=): each message waits before it shows, and one deleted, purged or
  // hidden meanwhile never does. Messages from before the page opened only wait out what is left of it.
  // live: it arrived as it happened (not the backlog sent on connect). at: when it arrived.
  const hold = F.holdQueue();
  let holdTimer = 0;
  function chatIn(m, live, at) {
    if (m.hidden || chat.seen.has(m.id)) return;
    const now = Date.now();
    if (!themed && !DEMO) { early.push({ m, live, at: at || now }); return; }
    const wait = theme.chat.delay * 1000;
    const until = !wait ? 0 : live ? (at || now) + wait : (m.t || now) + wait;
    if (until <= now) { chatAdd(m, live); return; }
    hold.add(m, until);
    holdNext();
  }
  function holdNext() {
    clearTimeout(holdTimer);
    const at = hold.next();
    if (at === Infinity) return;
    holdTimer = setTimeout(() => { hold.due(Date.now()).forEach((m) => chatAdd(m, true, Date.now())); holdNext(); }, Math.max(0, at - Date.now()) + 10);
  }

  function draw(item, animate) {
    const box = root.firstChild;
    if (!chatShows(item.m)) { item.el = null; return; }
    const el = message(item.m, 'cc-msg');
    if (animate) el.classList.add('cc-new');
    if (item.el && item.el.isConnected) item.el.replaceWith(el);
    else if (theme.chat.direction === 'top') box.prepend(el); else box.appendChild(el);
    item.el = el;
    clearTimeout(item.timer);
    const life = theme.chat.seconds * 1000;
    if (life && !STILL) item.timer = setTimeout(() => drop(item), Math.max(0, life - (Date.now() - item.born)));
  }

  function drop(item, quick) {
    clearTimeout(item.timer);
    chat.items = chat.items.filter((i) => i !== item);
    if (item.el) { if (quick) item.el.remove(); else leave(item.el); }
  }

  function trim() {
    const visible = chat.items.filter((i) => i.el);
    visible.slice(0, Math.max(0, visible.length - theme.chat.max)).forEach((i) => drop(i, true));
    if (chat.items.length > 200) chat.items.slice(0, chat.items.length - 200).forEach((i) => drop(i, true));
  }

  // ---- featured message ---------------------------------------------------------------------------------
  const featured = { m: null, el: null, timer: 0 };

  function feature(m) {                            // never delayed: the streamer picked it
    clearTimeout(featured.timer);
    if (featured.el) leave(featured.el);
    featured.m = m && !m.hidden ? m : null; featured.el = null;
    if (!featured.m) return;
    featured.el = message(m, 'cc-featured');
    featured.el.classList.add('cc-new');
    root.firstChild.appendChild(featured.el);
    if (theme.featured.seconds && !STILL) featured.timer = setTimeout(() => feature(null), theme.featured.seconds * 1000);
  }

  // ---- viewer counter -------------------------------------------------------------------------------------
  const crowd = { counts: {}, status: {}, total: 0, shownTotal: 0, raf: 0 };

  function short(n) {
    if (n == null) return '–';
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
    if (n >= 1e4) return (n / 1e3).toFixed(1).replace(/\.0$/, '') + 'K';
    return Number(n).toLocaleString('en-US');
  }

  function drawViewers() {
    const box = root.firstChild;
    box.replaceChildren();
    const platforms = T.PLATFORMS.filter((p) => crowd.counts[p] != null || crowd.status[p] === 'on');
    box.dataset.empty = String(!live && !platforms.length && !crowd.total);
    const total = doc.createElement('span'); total.className = 'cc-total';
    const dot = doc.createElement('i'); dot.className = 'cc-live';
    const n = doc.createElement('b'); n.className = 'cc-count'; n.textContent = short(crowd.shownTotal);
    const label = doc.createElement('small'); label.textContent = theme.viewers.label;
    total.append(dot, n, label);
    box.appendChild(total);
    if (!theme.viewers.perPlatform) return;
    platforms.forEach((p) => {
      const pill = doc.createElement('span'); pill.className = 'cc-vp'; pill.dataset.platform = p;
      pill.style.setProperty('--cc-p', theme.colors[p]); pill.style.setProperty('--cc-ink', T.ink(theme.colors[p]));
      if (theme.viewers.icon) { const icon = doc.createElement('span'); icon.className = 'cc-icon'; icon.appendChild(I.icon(p, doc)); pill.appendChild(icon); }
      else { const tag = doc.createElement('span'); tag.textContent = I.NAMES[p]; pill.appendChild(tag); }
      const count = doc.createElement('b'); count.textContent = short(crowd.counts[p]); pill.appendChild(count);
      box.appendChild(pill);
    });
  }

  function countTo(total) {                        // the total counts up or down instead of jumping
    crowd.total = total;
    cancelAnimationFrame(crowd.raf);
    const from = crowd.shownTotal, began = performance.now();
    const step = (now) => {
      const k = Math.min(1, (now - began) / 700), eased = 1 - Math.pow(1 - k, 3);
      crowd.shownTotal = Math.round(from + (total - from) * eased);
      const n = root.querySelector('.cc-count'); if (n) n.textContent = short(crowd.shownTotal);
      if (k < 1) crowd.raf = requestAnimationFrame(step);
    };
    if (STILL) { crowd.shownTotal = total; drawViewers(); } else crowd.raf = requestAnimationFrame(step);
  }

  // ---- alerts -----------------------------------------------------------------------------------------------
  const alerts = { queue: [], m: null, el: null, timer: 0, seen: new Set() };

  function alertShows(m) {
    if (m.kind !== 'event') return false;
    const kind = T.ALERTS.includes(m.alert) ? m.alert : 'other';
    return !!theme.alerts.types[kind];
  }

  function alertAdd(m, fresh) {
    if (alerts.seen.has(m.id) || m.hidden || !alertShows(m) || (!fresh && !DEMO)) return;
    alerts.seen.add(m.id);
    alerts.queue.push(m);
    if (alerts.queue.length > 20) alerts.queue.shift();
    if (!alerts.el) nextAlert();
  }

  function nextAlert() {
    const m = alerts.queue.shift();
    if (!m) return;
    alerts.m = m;
    alerts.el = alertCard(m);
    alerts.el.classList.add('cc-new');
    root.firstChild.appendChild(alerts.el);
    if (theme.alerts.sound && !PREVIEW && !STILL) chime(theme.alerts.volume);
    if (STILL) return;
    alerts.timer = setTimeout(() => {
      alerts.m = null;
      leave(alerts.el, () => { alerts.el = null; setTimeout(nextAlert, 350); });
    }, theme.alerts.seconds * 1000);
  }

  function alertCard(m) {
    const kind = T.ALERTS.includes(m.alert) ? m.alert : 'other';
    const el = doc.createElement('div'); el.className = 'cc-alert'; el.dataset.alert = kind; el.dataset.platform = m.p; el.dataset.id = m.id;
    colourFor(el, m);
    const icon = doc.createElement('div'); icon.className = 'cc-alert-icon'; icon.appendChild(I.icon(m.p, doc));
    const body = doc.createElement('div'); body.className = 'cc-alert-body';
    const title = doc.createElement('div'); title.className = 'cc-alert-title';
    const template = theme.alerts.labels[kind];
    T.fillParts(template, { name: m.name, amount: m.amount, text: m.text, platform: I.NAMES[m.p] || '' }).forEach((part) => {
      if (part.text !== undefined) { title.appendChild(doc.createTextNode(part.text)); return; }
      const span = doc.createElement('span'); span.className = 'cc-alert-' + part.key; span.textContent = part.value; title.appendChild(span);
    });
    body.appendChild(title);
    if (theme.alerts.showText && m.text && !/\{text\}/.test(template)) {
      const text = doc.createElement('div'); text.className = 'cc-alert-text'; words(text, m); body.appendChild(text);
    }
    el.append(icon, body);
    return el;
  }

  let audio = null;
  function chime(volume) {                         // three quick bright notes, made here rather than loaded
    try {
      audio = audio || new AudioContext();
      const now = audio.currentTime;
      [659.25, 880, 1318.5].forEach((f, i) => {
        const o = audio.createOscillator(), g = audio.createGain(), at = now + i * 0.11;
        o.type = i === 2 ? 'sine' : 'triangle'; o.frequency.value = f;
        g.gain.setValueAtTime(0.0001, at); g.gain.exponentialRampToValueAtTime(Math.max(0.0002, volume * 0.5), at + 0.015);
        g.gain.exponentialRampToValueAtTime(0.0001, at + 0.5 + i * 0.15);
        o.connect(g).connect(audio.destination); o.start(at); o.stop(at + 0.8);
      });
    } catch (e) { /* no audio here: the alert still shows */ }
  }

  // ---- whole widget --------------------------------------------------------------------------------------
  function frame() {
    const cls = { chat: 'cc-chat', featured: 'cc-featured-area', viewers: 'cc-viewers', alerts: 'cc-alerts' }[WIDGET];
    const box = doc.createElement('div'); box.className = cls;
    root.replaceChildren(box);
  }

  function redraw() {                              // after a theme change: same data, new look, no animation
    frame();
    if (WIDGET === 'chat') { chat.items.forEach((i) => { i.el = null; draw(i, false); }); trim(); }
    else if (WIDGET === 'featured' && featured.m) { const m = featured.m; featured.el = null; feature(m); if (featured.el) featured.el.classList.remove('cc-new'); }
    else if (WIDGET === 'viewers') drawViewers();
    else if (WIDGET === 'alerts' && alerts.m) { alerts.el = alertCard(alerts.m); root.firstChild.appendChild(alerts.el); }
  }

  function handle(m) {
    if (!m || typeof m !== 'object') return;
    if (m.type === 'msg') {
      if (WIDGET === 'chat') chatIn(m, primed);
      else if (WIDGET === 'alerts') alertAdd(m, primed && Date.now() - (m.t || 0) < 20000);
    } else if (m.type === 'status') {
      primed = true; live = !!m.live; crowd.status = m.status || {};
      if (WIDGET === 'viewers') drawViewers();
    } else if (m.type === 'viewers') {
      crowd.counts = m.counts || {};
      if (WIDGET === 'viewers') { drawViewers(); countTo(m.total || 0); }
    } else if (m.type === 'delete' || m.type === 'purge' || m.type === 'hide') {
      early = early.filter((e) => !F.takes(m, e.m));
      hold.drop((held) => F.takes(m, held));
      chat.items.filter((i) => F.takes(m, i.m)).forEach((i) => drop(i));
      if (featured.m && F.takes(m, featured.m)) feature(null);
    } else if (m.type === 'clear') {
      early = []; hold.clear();
      chat.items.slice().forEach((i) => drop(i, true));
      chat.seen.clear();
    } else if (m.type === 'emotes') {
      emotes = F.emoteMap(m.emotes);
      if (chat.items.length || featured.m) redraw();
    } else if (m.type === 'feature' && WIDGET === 'featured') {
      feature(m.msg && m.msg.text !== undefined ? m.msg : null);
    } else if (m.type === 'theme' && !PREVIEW) {
      if (!q.get('theme') || q.get('theme') === m.name) loadTheme();
    }
  }

  function connect(wait) {
    const feed = new EventSource('/events');
    feed.onopen = () => { wait = 2000; };
    feed.onmessage = (e) => { let m; try { m = JSON.parse(e.data); } catch (err) { return; } handle(m); };
    feed.onerror = () => { feed.close(); setTimeout(() => { loadTheme(); connect(Math.min(wait * 2, 30000)); }, wait); };   // the hub may start after OBS does
  }

  // ---- made-up data, for ?demo and the Theme Studio -----------------------------------------------------------
  const PEOPLE = [
    { p: 'twitch', name: 'pixel_pirate', color: '#ff7f50' }, { p: 'youtube', name: 'Maya Chen', badges: ['member'] },
    { p: 'x', name: 'Dev Daily', handle: 'devdaily' }, { p: 'kick', name: 'turbo_kat', color: '#53fc18' },
    { p: 'twitch', name: 'nightowl_42', color: '#1e90ff', badges: ['moderator'] }, { p: 'youtube', name: 'Sam Ortiz' },
    { p: 'x', name: 'Lena Park', handle: 'lenapark' }, { p: 'twitch', name: 'kiwi_codes', color: '#9acd32', badges: ['subscriber'] },
    { p: 'kick', name: 'quietstorm', color: '#f4a261' }, { p: 'youtube', name: 'Rafael Gomes', badges: ['moderator'] },
    { p: 'twitch', name: 'AriaPlays', color: '#ff69b4', badges: ['vip'] }, { p: 'x', name: 'byte bandit', handle: 'bytebandit' },
  ];
  const LINES = [                                  // one line per person above, in the same order
    'first time catching this live! HeyGuys', 'hello from Lisbon 👋 the overlay looks so clean', 'one chat for every platform, finally',
    'W stream, the audio sounds great', 'welcome in everyone, be nice in chat', 'can you explain that last part again?',
    'lurking but loving it', 'that boss fight Kappa', 'how long have you been streaming today?', 'drop the settings pls 🙏',
    'gg that was close', 'chat is moving fast today',
  ];
  const EMOTES = { Kappa: '25', HeyGuys: '30259' };
  const demoAlerts = [
    { alert: 'superchat', p: 'youtube', name: 'Maya Chen', amount: '$10.00', text: 'Thanks for the tutorial, it finally clicked!' },
    { alert: 'sub', p: 'twitch', name: 'kiwi_codes' },
    { alert: 'raid', p: 'twitch', name: 'AriaPlays', amount: '42' },
    { alert: 'member', p: 'youtube', name: 'Rafael Gomes' },
    { alert: 'cheer', p: 'twitch', name: 'pixel_pirate', amount: '500 bits', text: "Let's go!" },
    { alert: 'gift', p: 'twitch', name: 'nightowl_42', amount: '5 subs' },
    { alert: 'follow', p: 'kick', name: 'quietstorm' },
  ].map((a, i) => ({ type: 'msg', kind: 'event', id: 'demo-alert-' + i, t: Date.now(), text: '', ...a }));

  function emotesFor(text) {                       // Twitch's "id:from-to" list for the demo lines, counted in code points
    const chars = [...text], spots = {};
    let at = 0;
    text.split(' ').forEach((word) => {
      const len = [...word].length;
      if (EMOTES[word]) (spots[EMOTES[word]] = spots[EMOTES[word]] || []).push(at + '-' + (at + len - 1));
      at += len + 1;
    });
    return chars.length ? Object.entries(spots).map(([id, s]) => id + ':' + s.join(',')).join('/') : '';
  }

  let tick = 0;
  function demoLine(i) {
    const who = PEOPLE[i % PEOPLE.length], text = LINES[(i + Math.floor(i / PEOPLE.length) * 5) % LINES.length];
    return { type: 'msg', kind: 'chat', id: 'demo-' + i + '-' + Date.now(), t: Date.now(), text, emotes: emotesFor(text), badges: [], color: '',
             first: i === 0 ? 'ever' : '', ...who };
  }

  function demo() {
    primed = true; live = true;
    const counts = { twitch: 128, youtube: 342, kick: 41, x: 87 };
    const sum = () => Object.values(counts).reduce((a, b) => a + b, 0);
    if (WIDGET === 'chat') {
      for (tick = 0; tick < 8; tick++) chatAdd(demoLine(tick), false);
      chatAdd({ type: 'msg', kind: 'event', alert: 'resub', amount: '6', id: 'demo-ev', t: Date.now(), p: 'twitch', name: 'kiwi_codes', text: '', badges: [] }, false);
      if (!STILL) setInterval(() => chatIn(demoLine(tick++), true), 2400);   // new lines wait out the delay, as on stream
    } else if (WIDGET === 'featured') {
      const picks = [5, 1, 9, 3].map((i) => demoLine(i));
      feature(picks[0]);
      if (!STILL) { let n = 1; setInterval(() => feature(picks[n++ % picks.length]), 6000); }
    } else if (WIDGET === 'viewers') {
      handle({ type: 'status', live: true, status: { twitch: 'on', youtube: 'on', kick: 'on', x: 'on' } });
      handle({ type: 'viewers', counts: { ...counts }, total: sum() });
      if (!STILL) setInterval(() => {
        Object.keys(counts).forEach((p) => { counts[p] = Math.max(3, counts[p] + Math.round((Math.random() - 0.4) * counts[p] * 0.06)); });
        handle({ type: 'viewers', counts: { ...counts }, total: sum() });
      }, 3000);
    } else if (WIDGET === 'alerts') {
      alertAdd(demoAlerts[0], true);
      if (!STILL) { let n = 1; setInterval(() => { const a = { ...demoAlerts[n++ % demoAlerts.length] }; a.id += '-' + n; alertAdd(a, true); }, (theme.alerts.seconds + 2) * 1000); }
    }
  }

  // The Theme Studio sends the theme it is editing; only a page on this same address may.
  window.addEventListener('message', (e) => {
    if (e.origin !== location.origin || !e.data || e.data.crosschat !== 'theme') return;
    useTheme(e.data.theme);
  });

  frame();
  T.apply(theme, doc);
  if (DEMO) { loadTheme().then(demo); }
  else { loadTheme(); connect(2000); }
  if (PREVIEW && window.parent !== window) window.parent.postMessage({ crosschat: 'ready', widget: WIDGET }, location.origin);
})();
