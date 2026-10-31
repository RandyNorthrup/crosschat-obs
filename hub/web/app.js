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
  const NAMES = { twitch: ['Twitch', 'TW'], youtube: ['YouTube', 'YT'], kick: ['Kick', 'K'], x: ['X', 'X'], facebook: ['Facebook', 'FB'] };
  const LIMIT = { twitch: 500, youtube: 200, x: 140 };     // platforms a reply can go to, and the longest message each takes
  const QUICK_MAX = 30, QUICK_LENGTH = 100;

  const name = (p) => (NAMES[p] ? NAMES[p][0] : p);
  const openPlatforms = (states) => Object.keys(LIMIT).filter((p) => (states || {})[p] === 'on');   // chats that can take a reply now
  const targetsFor = (states, replyTo) => (replyTo ? [replyTo.p] : openPlatforms(states));
  const tooLong = (text, to) => to.filter((p) => LIMIT[p] && [...text].length > LIMIT[p]);
  const clean = (text) => String(text || '').replace(/\s+/g, ' ').trim();

  // What can carry a message to platform p right now: { ok, why }.
  function route(p, ctx) {
    if (!LIMIT[p]) return { ok: false, why: name(p) + ' chat can only be read from CrossChat' };
    if (p === 'twitch' && ctx.twitch === 'on') return { ok: true };
    if (ctx.executor) return { ok: true };
    return { ok: false, why: ctx.remote ? 'Needs the CrossChat window open on the streaming PC' + (p === 'twitch' ? ', or Twitch connected in Settings' : '')
      : 'Needs this window open in Chrome or Edge with the CrossChat extension' + (p === 'twitch' ? ', or Twitch connected in Settings' : '') };
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
    if (m.p === 'kick') return off("Kick chat can't be moderated from CrossChat yet");
    if (m.p === 'twitch') {
      const why = ctx.twitch === 'on' ? '' : ctx.remote ? 'Connect Twitch on the streaming PC (Settings) to moderate' : 'Connect Twitch in Settings to moderate';
      const ok = !why;
      return [
        { action: 'delete', label: 'Delete message', ok: ok && !!m.mid, why: why || (m.mid ? '' : 'Twitch gave this message no id') },
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
        { action: 'timeout', seconds: 300, label: 'Timeout 5 minutes (YouTube’s fixed length)', ok, why },
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
             ban: 'banned ' + who, unban: 'unbanned ' + who }[action] || action + ' ' + who;
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

  return { NAMES, LIMIT, QUICK_MAX, QUICK_LENGTH, name, openPlatforms, targetsFor, tooLong, clean, route, canReply, modMenu,
           duration, describe, cleanQuick, inView, mention, secondsLeft, readable, pieces };
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

  const ctx = { remote: false, device: null, version: '', lanUrl: null, executor: false, executorKnown: false, twitch: 'off',
                bridge: !!document.documentElement.dataset.crosschat, states: {}, unpaired: false };
  let counts = {}, starred = new Set(), quick = [], devices = [], twitchAuth = { state: 'off' }, pairTimer = null;
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
    job.timer = setTimeout(() => finish(id, null), 25000);
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
      else note(who + ': could not ' + ({ delete: 'remove that message', timeout: 'time out ' + job.who, ban: 'ban ' + job.who, unban: 'unban ' + job.who }[job.action] || job.action)
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
  const jobs = {};
  let jobN = 0;
  function runJob(job) {
    const n = ++jobN;
    jobs[n] = { job, timer: setTimeout(() => done(n, null), 25000) };
    if (job.kind === 'mod') {
      window.postMessage({ crosschat: 'mod', n, p: job.p, action: job.action, message_id: job.message_id || '', user_id: job.user_id || '',
                           name: job.name || '', seconds: job.seconds || 0, reason: job.reason || '' }, location.origin);
    } else {
      window.postMessage({ crosschat: 'send', n, to: job.to || [], text: job.text || '', reply: job.reply || null, dry: !!job.dry }, location.origin);
    }
  }
  function done(n, answer) {
    const j = jobs[n];
    if (!j) return;
    delete jobs[n]; clearTimeout(j.timer);
    const why = 'the CrossChat extension did not answer';
    if (!answer) answer = j.job.kind === 'mod' ? { ok: false, why } : Object.fromEntries((j.job.to || []).map((p) => [p, { ok: false, why }]));
    api('/outbox/result', { job_id: j.job.id, answer });
  }
  window.addEventListener('message', (e) => {
    if (e.source !== window || !e.data || (e.data.crosschat !== 'sent' && e.data.crosschat !== 'modded')) return;
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
    list.querySelectorAll('.emote').forEach((img) => { img.src = img.src.replace(/\/(dark|light)\//, lightNow() ? '/light/' : '/dark/'); });
  }

  function words(into, m) {                       // the message text, with Twitch emotes swapped for their pictures
    A.pieces(m.text, m.p === 'twitch' ? m.emotes : '').forEach((piece) => {
      if (piece.text != null) { into.append(piece.text); return; }
      const img = el('img', 'emote'); img.alt = piece.alt;
      img.src = 'https://static-cdn.jtvnw.net/emoticons/v2/' + piece.emote + '/default/' + (lightNow() ? 'light' : 'dark') + '/1.0';
      into.append(img);
    });
  }

  // ---- who is watching, where a reply can go -------------------------------------------------------------------------
  const targets = () => A.targetsFor(ctx.states, replyTo);

  function drawPlatforms() {
    const bar = $('platforms'), only = $('targets');
    bar.textContent = ''; only.textContent = '';
    Object.keys(ctx.states).forEach((p) => {
      const state = ctx.states[p];
      const pill = el('div', 'pill ' + (state === 'on' ? 'on' : state === 'retry' ? 'retry' : ''));
      pill.style.setProperty('--c', css(p));
      pill.title = A.name(p) + ' chat: ' + ({ on: 'connected', waiting: 'waiting for the stream', retry: 'reconnecting', off: p === 'x' ? 'no livestream there (Go live on X starts one)' : 'off' }[state] || state);
      pill.append(el('i'), el('span', '', A.name(p)), el('b', '', counts[p] == null ? '–' : counts[p]));
      bar.append(pill);
      if (!A.LIMIT[p]) return;
      const b = el('button', 'to'); b.type = 'button'; b.style.setProperty('--c', css(p)); b.append(el('i'), A.name(p));
      b.disabled = sending || state !== 'on';
      b.title = state === 'on' ? 'Send what you typed to ' + A.name(p) + ' only' : A.name(p) + ' chat is not open right now';
      b.onclick = () => post([p]);
      only.append(b, ' ');
    });
    drawEntry();
  }

  function drawEntry() {
    const to = targets(), text = A.clean(say.value), over = A.tooLong(text, to), n = [...text].length;
    $('left').textContent = !n ? '' : over.length ? n + ' characters: too long for ' + over.map((p) => A.name(p) + ' (' + A.LIMIT[p] + ')').join(', ') : n;
    $('left').className = over.length ? 'over' : '';
    $('all').textContent = sending ? 'Sending…' : replyTo ? 'Reply on ' + A.name(replyTo.p) : 'Send to all';
    $('all').disabled = $('send').disabled = sending || !to.length;
    $('all').title = $('send').title = to.length ? 'Goes to: ' + to.map(A.name).join(', ') : 'No chat is open right now';
    document.querySelectorAll('#quick .chip:not(.edit)').forEach((c) => { c.disabled = !A.openPlatforms(ctx.states).length; });
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
    row.setAttribute('aria-label', m.name + ' on ' + A.name(m.p) + ': ' + (m.system ? m.system + ' ' : '') + m.text);
    if (m.question) row.classList.add('q');
    const tag = el('div', 'tags'); tag.append(tagFor(m.p));
    const body = el('div', 'body');
    (m.badges || []).filter((b) => /^(broadcaster|owner|moderator|vip|verified|member|subscriber|founder)$/.test(b))
      .forEach((b) => body.append(el('span', 'badge', b === 'broadcaster' || b === 'owner' ? 'you' : b === 'moderator' ? 'mod' : b === 'subscriber' ? 'sub' : b)));
    const who = el('span', 'name', m.name); who.dataset.color = m.color || ''; who.style.color = nameColor(m.color);
    body.append(who);
    if (m.system && m.system !== m.text) body.append(el('span', 'system', m.system + (m.text ? ' · ' : '')));
    words(body, m);
    body.append(el('span', 'time', new Date(m.t).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })));
    const flags = el('span', 'flags');
    if (m.question) flags.append(el('span', 'flag q', 'Q'));
    const star = el('span', 'flag star', '★'); star.hidden = !starred.has(m.id); flags.append(star);
    body.append(flags);
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
    if (ding && Date.now() - m.t < 5000) beep();
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
      chip.addEventListener('click', () => { if (held) { held = false; return; } post(A.openPlatforms(ctx.states), text); });
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
  const ctxNow = () => ({ remote: ctx.remote, executor: ctx.executor || DEMO, twitch: twitchAuth.state, states: ctx.states });

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
    if (m.system) quote.append(el('b', '', m.system + (m.text ? ' · ' : '')));
    words(quote, m);
    menu.textContent = '';
    const close = () => $('sheet').close();
    const can = A.canReply(m, c), yes = { ok: true };
    menu.append(item('↩', 'Reply', can, () => { close(); setReply(m); }));
    const on = m.id === featuredId;
    menu.append(item('▣', on ? 'Hide from stream' : 'Show on stream', yes, () => { close(); featureIt(on ? null : m.id); }, { hint: on ? '' : 'Big, as the featured message' }));
    const st = starred.has(m.id);
    menu.append(item(st ? '★' : '☆', st ? 'Remove from Answer later' : 'Answer later', yes, () => { close(); toggleStar(m.id); }));
    menu.append(item('⧉', 'Copy text', yes, () => { close(); copy((m.system ? m.system + ' ' : '') + m.text); }));
    group(menu, 'Moderate');
    A.modMenu(m, c).forEach((entry) => {
      const icon = { delete: '🗑', timeout: '⏱', ban: '⛔', unban: '↺' }[entry.action] || '•';
      menu.append(item(icon, entry.label, entry, async () => {
        close();
        if (entry.custom) {
          const minutes = await ask({ title: 'Time out ' + m.name, text: 'How long on ' + A.name(m.p) + '? (1 minute to 14 days)', ok: 'Time out', input: true });
          if (minutes) moderate(m, entry, Math.min(1209600, Math.max(60, Math.round(minutes * 60))));
        } else if (entry.action === 'ban') {
          if (await ask({ title: (m.p === 'youtube' ? 'Hide ' : 'Ban ') + m.name + '?', text: m.p === 'youtube' ? 'They won\'t be able to chat on your channel until you unhide them in YouTube Studio.' : 'They won\'t be able to chat on your Twitch channel until you unban them.', ok: m.p === 'youtube' ? 'Hide user' : 'Ban' })) moderate(m, entry, 0);
        } else moderate(m, entry, entry.seconds || 0);
      }, { danger: entry.danger }));
    });
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
    $('twitch-hint').textContent = blocked ? twitchAuth.why + ' Twitch replies still go out through the browser extension.'
      : ctx.remote ? 'Connecting Twitch is done on the streaming PC (Settings there).'
      : 'Connected, CrossChat posts your Twitch replies and moderates Twitch chat itself, without the browser extension.';
  }
  $('twitch-connect').onclick = async () => { const a = await api('/twitch/connect', {}); if (!a.ok) note('Twitch: ' + (a.why || 'could not start') + '.', 'bad'); };
  $('twitch-disconnect').onclick = async () => { if (await ask({ title: 'Disconnect Twitch?', text: 'Twitch replies then go through the browser extension again, and Twitch moderation stops.', ok: 'Disconnect' })) api('/twitch/disconnect', {}); };
  $('twitch-open').onclick = () => window.open(twitchAuth.verification_uri || 'https://www.twitch.tv/activate', '_blank', 'noopener');

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

  function drawSettings() {
    showTheme(); showDing(); drawTwitch(); drawDevices();
    $('devices-section').hidden = ctx.remote;
    $('studio-row').hidden = ctx.remote;
    $('about').textContent = 'CrossChat ' + (ctx.version || '') + ' · ' + (ctx.remote ? 'this device: ' + (ctx.device || 'paired device')
      : 'the streaming PC' + (ctx.lanUrl ? ' · other devices reach it at ' + ctx.lanUrl : ''));
  }

  // ---- notices and the mode (this PC, or a paired device) -----------------------------------------------------------
  function drawNotice() {
    const n = $('notice'), text = n.querySelector('span');
    let say_ = '';
    if (ctx.unpaired) say_ = 'This device is no longer paired. Pair it again from Settings on the streaming PC.';
    else if (!DEMO && ctx.executorKnown && !ctx.executor) {
      say_ = ctx.remote ? 'Replies to YouTube and X need the CrossChat window open on the streaming PC (Chrome or Edge with the extension).'
        : ctx.bridge ? '' : 'Replies to YouTube and X go out through the CrossChat window in Chrome or Edge with the extension: Start menu → CrossChat → Open chat.';
      if (say_ && twitchAuth.state !== 'on') say_ += ' Twitch too, until Twitch is connected in Settings.';
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
        ctx.states = m.status || {}; drawPlatforms(); youtubeBox(m.yt || '');
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
      case 'executor': ctx.executor = !!m.present; ctx.executorKnown = true; drawNotice(); drawPlatforms(); break;
      case 'twitch_auth': twitchAuth = m; drawTwitch(); drawNotice(); break;
      case 'devices': devices = m.devices || []; drawDevices(); break;
      case 'pair': showPair(m); break;
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
    feed = new EventSource('/events' + (executorRole() ? '?executor=1' : ''));
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
    return ok();
  }

  function demo() {
    const remote = DEMO_KIND === 'remote';
    Object.assign(ctx, { remote, device: remote ? 'Phone' : null, version: '1.1.0', lanUrl: 'http://192.168.1.20:4467/', executor: true, executorKnown: true });
    applyMode(); connected(true);
    const t = Date.now() - 9 * 60000, at = (min) => t + min * 60000;
    handle({ type: 'status', live: true, status: { twitch: 'on', youtube: 'on', kick: 'on', x: 'on' } });
    handle({ type: 'viewers', counts: { twitch: 128, youtube: 342, kick: 41, x: 87 }, total: 598 });
    handle({ type: 'twitch_auth', state: 'on', login: 'you' });
    handle({ type: 'quick', replies: ['Welcome in! 👋', 'Thanks for the follow!', 'GG', 'Be right back', 'Links are in the panels below', '❤'] });
    handle({ type: 'devices', devices: [{ id: 'd1', name: 'Phone', created: at(-3000) / 1000, last_seen: Date.now() / 1000 },
                                          { id: 'd2', name: 'Laptop', created: at(-9000) / 1000, last_seen: at(-1500) / 1000 }] });
    [{ kind: 'note', p: 'system', text: 'Stream started. Chat from every platform shows up here.', t: at(0) },
     { p: 'twitch', name: 'pixel_pirate', color: '#ff7f50', text: 'first! what are we building today?', question: true, t: at(1), mid: 'a1', uid: '101' },
     { p: 'youtube', name: 'Maya Chen', badges: ['member'], text: 'Watching from Lisbon 👋 love the new overlay', t: at(1.5), mid: 'y1' },
     { p: 'x', name: 'Dev Daily', handle: 'devdaily', text: 'One chat for every platform, finally', t: at(2) },
     { p: 'kick', name: 'turbo_kat', color: '#53fc18', text: 'W stream, audio sounds great', t: at(3) },
     { p: 'twitch', kind: 'event', name: 'nightowl_42', system: 'subscribed for 6 months!', text: 'half a year already', t: at(4) },
     { p: 'twitch', name: 'nightowl_42', color: '#1e90ff', badges: ['moderator'], text: 'welcome in, new folks 🙂', t: at(4.5), mid: 'a2', uid: '102' },
     { p: 'youtube', name: 'Sam Ortiz', text: 'can you show how replies reach every platform?', question: true, t: at(6), id: 'yt-sam', mid: 'y2' },
     { p: 'twitch', name: 'bot_4417', color: '#7fff00', text: 'cheap followers!!! dm me for a deal', t: at(6.5), id: 'tw-spam', mid: 'a3', uid: '103' },
     { p: 'x', name: 'Lena Park', handle: 'lenapark', text: 'does the overlay work with Streamlabs too?', question: true, t: at(7) },
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
    if (DEMO_KIND === 'settings' || DEMO_KIND === 'pair') { drawSettings(); openDialog($('settings')); }
    if (DEMO_KIND === 'pair') { api('/pair/start', {}); $('pair').scrollIntoView({ block: 'center' }); }
    if (DEMO_KIND === 'quick') openQuickEditor();
  }

  start();
})(globalThis.CrossChatApp);
