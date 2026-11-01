// Theme Studio: pick a theme, change it with live preview, save it for OBS. The preview frames are the real overlay
// page (/overlay/<widget>?preview) showing made-up chat; the Studio sends them the theme being edited.
(() => {
  const T = window.CrossChatTheme, doc = document, $ = (id) => doc.getElementById(id);
  const WIDGETS = {
    chat: { label: 'Chat feed', size: [450, 800], at: [40, 230], test: 'chat', help: 'Chat from every platform.' },
    featured: { label: 'Featured message', size: [900, 260], at: [510, 790], test: 'featured', help: 'A message you pick in the chat window.' },
    viewers: { label: 'Viewer counter', size: [600, 120], at: [40, 36], test: 'viewers', help: 'Everyone watching, per platform.' },
    alerts: { label: 'Alerts', size: [800, 300], at: [720, 40], test: 'alert', help: 'Subs, members, Super Chats, raids.' },
  };
  const BRAND = { twitch: '#9146ff', youtube: '#ff0033', kick: '#53fc18', x: '#e7e9ea', tiktok: '#fe2c55', facebook: '#0866ff', instagram: '#ff0069',
                  rumble: '#85c742' };
  const PLATFORM_NAMES = { twitch: 'Twitch', youtube: 'YouTube', kick: 'Kick', x: 'X', tiktok: 'TikTok', facebook: 'Facebook', instagram: 'Instagram',
                           rumble: 'Rumble' };
  const FONTS = [
    ['Segoe UI Variable (Windows default)', T.DEFAULTS.font.family],
    ['Segoe UI Variable Display', '"Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif'],
    ['Segoe UI', '"Segoe UI", system-ui, sans-serif'],
    ['Bahnschrift', '"Bahnschrift", "Segoe UI", sans-serif'],
    ...['Arial', 'Arial Black', 'Calibri', 'Candara', 'Corbel', 'Franklin Gothic Medium', 'Impact', 'Tahoma', 'Trebuchet MS', 'Verdana', 'Comic Sans MS',
        'Segoe Print', 'Ink Free'].map((f) => [f, '"' + f + '", "Segoe UI", sans-serif']),
    ...['Georgia', 'Cambria', 'Constantia', 'Sitka Text'].map((f) => [f, '"' + f + '", Georgia, serif']),
    ...['Cascadia Mono', 'Cascadia Code', 'Consolas', 'Lucida Console'].map((f) => [f, '"' + f + '", Consolas, monospace']),
  ];
  const WEIGHTS = [[300, 'Light'], [400, 'Regular'], [500, 'Medium'], [600, 'Semibold'], [700, 'Bold'], [800, 'Extra bold'], [900, 'Black']];
  const WORDS = {
    platform: 'Platform colour', user: "Viewer's own colour", fixed: 'One colour for everyone',
    card: 'Card', bubble: 'Bubble', line: 'Plain text', compact: 'Compact (one line)',
    icon: 'Platform icon', text: 'Text tag (TW, YT…)', bar: 'Coloured bar only', none: 'Nothing',
    bottom: 'Newest at the bottom', top: 'Newest at the top', left: 'Left', right: 'Right',
    slide: 'Slide', fade: 'Fade', pop: 'Pop', banner: 'Full-width banner', row: 'In a row', stack: 'Stacked', total: 'Total only',
  };
  const ALERT_NAMES = { sub: 'Subs', resub: 'Resubs', gift: 'Gift subs', raid: 'Raids', cheer: 'Bits', member: 'Members', superchat: 'Super Chats', follow: 'Follows', other: 'Other events' };

  // Every control, by section. path = where it lives in the theme.
  const SECTIONS = [
    { title: 'Name', open: true, fields: [{ path: 'label', type: 'text', label: 'Display name', help: 'Shown in theme lists.' }] },
    { title: 'Text', open: true, fields: [
      { path: 'font.family', type: 'font', label: 'Font' },
      { path: 'font.google', type: 'text', label: 'Google Font (optional)', placeholder: 'e.g. Inter, Outfit, Nunito', help: 'Loaded from fonts.google.com when OBS shows the overlay. Leave empty to use the font above.' },
      { path: 'font.size', type: 'range', label: 'Size (px)' },
      { path: 'font.weight', type: 'weight', label: 'Message weight' },
      { path: 'font.nameWeight', type: 'weight', label: 'Name weight' },
      { path: 'font.lineHeight', type: 'range', label: 'Line spacing' },
    ] },
    { title: 'Colours', open: true, fields: [
      { path: 'colors.text', type: 'color', label: 'Text' },
      { path: 'colors.name', type: 'select', label: 'Names' },
      { path: 'colors.nameColor', type: 'color', label: 'Name colour', when: (t) => t.colors.name === 'fixed' },
      { path: 'colors.background', type: 'color', label: 'Background' },
      { path: 'colors.backgroundOpacity', type: 'range', label: 'Background opacity', percent: true, help: '0% for no background: then use an outline.' },
      { path: 'colors.accent', type: 'color', label: 'Accent', help: 'Badges, highlights, alert amounts.' },
      { path: 'colors.outline', type: 'color', label: 'Text outline colour', when: (t) => t.colors.outlineWidth > 0 },
      { path: 'colors.outlineWidth', type: 'range', label: 'Text outline width (px)' },
      { path: 'colors.shadow', type: 'range', label: 'Shadow', percent: true },
    ] },
    { title: 'Platform colours', fields: [
      { path: 'colors.twitch', type: 'color', label: 'Twitch' }, { path: 'colors.youtube', type: 'color', label: 'YouTube' },
      { path: 'colors.kick', type: 'color', label: 'Kick' }, { path: 'colors.x', type: 'color', label: 'X' },
      { path: 'colors.tiktok', type: 'color', label: 'TikTok' }, { path: 'colors.facebook', type: 'color', label: 'Facebook' },
      { path: 'colors.instagram', type: 'color', label: 'Instagram' }, { path: 'colors.rumble', type: 'color', label: 'Rumble' },
      { type: 'button', label: 'Use the brand colours', run: () => { Object.assign(work.colors, BRAND); changed(); fill(); } },
    ] },
    { title: 'Messages', fields: [
      { path: 'message.layout', type: 'select', label: 'Layout' },
      { path: 'message.radius', type: 'range', label: 'Corner rounding (px)' },
      { path: 'message.padding', type: 'range', label: 'Padding (px)' },
      { path: 'message.gap', type: 'range', label: 'Space between messages (px)' },
      { path: 'message.accentBar', type: 'toggle', label: 'Platform colour bar' },
      { path: 'message.accentWidth', type: 'range', label: 'Bar width (px)', when: (t) => t.message.accentBar || t.message.platform === 'bar' },
      { path: 'message.badges', type: 'toggle', label: 'Badges (mod, sub, member…)' },
      { path: 'message.emoteSize', type: 'range', label: 'Emote size (px)' },
      { path: 'message.timestamps', type: 'toggle', label: 'Times' },
      { path: 'message.firstHighlight', type: 'toggle', label: 'Highlight first-time chatters', help: 'A NEW tag and a ring on a viewer’s first message in your channel (Twitch says when).' },
    ] },
    { title: 'Platform tags', fields: [{ path: 'message.platform', type: 'select', label: 'Show the platform as' }] },
    { title: 'Chat feed', fields: [
      { path: 'chat.direction', type: 'select', label: 'Order' },
      { path: 'chat.align', type: 'select', label: 'Side' },
      { path: 'chat.max', type: 'range', label: 'Messages on screen' },
      { path: 'chat.seconds', type: 'range', label: 'Seconds each message stays (0 = stays)' },
      { path: 'chat.animationIn', type: 'select', label: 'Arrives with' },
      { path: 'chat.animationOut', type: 'select', label: 'Leaves with' },
      { path: 'chat.platforms', type: 'platforms', label: 'Platforms shown' },
      { path: 'chat.events', type: 'toggle', label: 'Subs, raids and other events in the feed' },
      { path: 'chat.delay', type: 'range', label: 'Delay before messages show (s)', help: 'Time to delete a message before it reaches the stream. 0 shows chat at once; the featured message never waits.' },
    ] },
    { title: 'Featured message', fields: [
      { path: 'featured.layout', type: 'select', label: 'Layout' },
      { path: 'featured.scale', type: 'range', label: 'Size (× chat text)' },
      { path: 'featured.platform', type: 'toggle', label: 'Say which platform' },
      { path: 'featured.seconds', type: 'range', label: 'Hide after seconds (0 = until cleared)' },
      { path: 'featured.animation', type: 'select', label: 'Arrives with' },
    ] },
    { title: 'Viewer counter', fields: [
      { path: 'viewers.layout', type: 'select', label: 'Layout' },
      { path: 'viewers.perPlatform', type: 'toggle', label: 'Count per platform' },
      { path: 'viewers.icon', type: 'toggle', label: 'Platform icons' },
      { path: 'viewers.label', type: 'text', label: 'Label after the total' },
    ] },
    { title: 'Alerts', fields: [
      { path: 'alerts.types', type: 'alerts', label: 'Show alerts for' },
      { path: 'alerts.seconds', type: 'range', label: 'Seconds on screen' },
      { path: 'alerts.animation', type: 'select', label: 'Arrives with' },
      { path: 'alerts.showText', type: 'toggle', label: "Show the viewer's message" },
      { path: 'alerts.sound', type: 'toggle', label: 'Chime', help: 'In OBS, tick “Control audio via OBS” on the alerts source to set its volume and route it.' },
      { path: 'alerts.volume', type: 'range', label: 'Chime volume', percent: true, when: (t) => t.alerts.sound },
      { path: 'alerts.labels', type: 'labels', label: 'Wording', help: '{name}, {amount}, {text} and {platform} are filled in.' },
    ] },
    { title: 'Custom CSS', fields: [{ path: 'css', type: 'css', label: 'Extra CSS for this theme', help: 'Class names and --cc-* variables are listed in docs/THEMES.md.' }] },
  ];

  let list = { default: 'classic', themes: [] }, current = { name: null, builtin: false }, work = T.merge({}), saved = JSON.stringify(work);
  let dirty = false, pushTimer = 0, backUrl = '';
  const frames = {};

  // ---- small helpers ------------------------------------------------------------------------------------------
  const get = (obj, path) => path.split('.').reduce((o, k) => (o == null ? o : o[k]), obj);
  const put = (obj, path, v) => { const ks = path.split('.'); const last = ks.pop(); ks.reduce((o, k) => o[k], obj)[last] = v; };
  const idFor = (path) => 'f-' + path.replace(/\./g, '-');
  function el(tag, attrs, ...kids) {
    const e = doc.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (v === undefined || v === null || (v === false && !(k in e))) return;
      if (k === 'text') e.textContent = v; else if (k in e) e[k] = v; else e.setAttribute(k, v);
    });
    kids.flat().forEach((k) => e.append(k));
    return e;
  }
  function say(text, kind) { const s = $('status'); s.textContent = text; s.className = kind || ''; clearTimeout(say.t); say.t = setTimeout(() => { s.textContent = ''; }, 6000); }
  async function call(path, body) {
    const r = await fetch(path, body === undefined ? { cache: 'no-store' } : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(path + ' answered ' + r.status);
    return r.json();
  }
  function ask(title, text, ok) {
    return new Promise((resolve) => {
      const d = $('ask-dialog');
      $('ask-title').textContent = title; $('ask-text').textContent = text; $('ask-ok').textContent = ok || 'OK';
      d.onclose = () => resolve(d.returnValue === 'ok');
      d.returnValue = ''; d.showModal();
    });
  }

  // ---- the controls -----------------------------------------------------------------------------------------
  function control(f) {
    const id = idFor(f.path || f.label), wrap = el('div', { class: 'field' });
    const label = el('label', { for: id, text: f.label });
    const range = T.RANGES[f.path];
    if (f.type === 'button') {
      wrap.append(el('button', { class: 'btn small', type: 'button', text: f.label, onclick: f.run }));
    } else if (f.type === 'text') {
      wrap.append(label, el('input', { id, type: 'text', placeholder: f.placeholder || '', maxLength: (T.TEXTS[f.path] || [140])[0], 'data-path': f.path }));
    } else if (f.type === 'css') {
      wrap.append(label, el('textarea', { id, spellcheck: false, 'data-path': f.path, placeholder: '.cc-name { text-transform: uppercase; }' }));
    } else if (f.type === 'color') {
      const text = el('input', { type: 'text', 'aria-label': f.label + ' (hex)', 'data-hex': f.path, maxLength: 7 });
      wrap.append(label, el('div', { class: 'colour' }, el('input', { id, type: 'color', 'data-path': f.path }), text));
    } else if (f.type === 'range') {
      const [lo, hi, step] = range, k = f.percent ? 100 : 1;
      wrap.append(label, el('div', { class: 'pair' },
        el('input', { id, type: 'range', min: lo * k, max: hi * k, step: step * k, 'data-path': f.path, 'data-k': k }),
        el('input', { type: 'number', min: lo * k, max: hi * k, step: step * k, 'aria-label': f.label + (f.percent ? ' (%)' : ''), 'data-num': f.path, 'data-k': k })));
    } else if (f.type === 'select' || f.type === 'weight' || f.type === 'font') {
      const options = f.type === 'weight' ? WEIGHTS.map(([v, n]) => [String(v), n]) : f.type === 'font' ? [...FONTS.map(([n, v]) => [v, n]), ['custom', 'Other font…']]
        : T.ENUMS[f.path].map((v) => [v, WORDS[v] || v]);
      const select = el('select', { id, 'data-path': f.path, 'data-kind': f.type }, options.map(([v, n]) => el('option', { value: v, text: n })));
      wrap.append(label, select);
      if (f.type === 'font') wrap.append(el('input', { type: 'text', 'aria-label': 'Font family (CSS)', 'data-family': f.path, hidden: true, placeholder: '"My Font", sans-serif' }));
    } else if (f.type === 'toggle') {
      wrap.className = 'field inline';
      wrap.append(label, el('span', { class: 'switch' }, el('input', { id, type: 'checkbox', role: 'switch', 'data-path': f.path }), el('i')));
    } else if (f.type === 'platforms' || f.type === 'alerts') {
      const names = f.type === 'platforms' ? T.PLATFORMS : T.ALERTS;
      const set = el('fieldset', { class: 'checks', 'data-group': f.path }, el('legend', { class: 'sr', text: f.label }),
        names.map((n) => el('label', {}, el('input', { type: 'checkbox', value: n }), f.type === 'platforms' ? PLATFORM_NAMES[n] || n : ALERT_NAMES[n])));
      wrap.append(el('span', { class: 'legend', 'aria-hidden': 'true', text: f.label }), set);
    } else if (f.type === 'labels') {
      wrap.append(el('span', { class: 'legend', text: f.label }));
      T.ALERTS.forEach((n) => {
        const lid = idFor('alerts.labels.' + n);
        wrap.append(el('label', { for: lid, text: ALERT_NAMES[n], style: 'font-weight:400' }), el('input', { id: lid, type: 'text', maxLength: 140, 'data-path': 'alerts.labels.' + n }));
      });
    }
    if (f.help) wrap.append(el('p', { class: 'help', text: f.help }));
    if (f.when) wrap.dataset.when = f.path;
    return wrap;
  }

  function build() {
    const form = $('controls');
    SECTIONS.forEach((s) => {
      const d = el('details', { open: s.open }, el('summary', { text: s.title }), el('div', { class: 'fields' }, s.fields.map(control)));
      form.append(d);
    });
    form.addEventListener('input', onInput);
    form.addEventListener('change', onInput);
  }

  // Put the values of `work` into the controls.
  function fill() {
    const form = $('controls');
    form.querySelectorAll('[data-path]').forEach((c) => {
      const v = get(work, c.dataset.path), k = Number(c.dataset.k || 1);
      if (c.type === 'checkbox') c.checked = !!v;
      else if (c.type === 'range') c.value = v * k;
      else if (c.dataset.kind === 'font') {          // a list entry when the first font named is one of ours
        const first = (stack) => String(stack).split(',')[0].replace(/["']/g, '').trim().toLowerCase();
        const known = FONTS.find(([, stack]) => first(stack) === first(v));
        c.value = known ? known[1] : 'custom';
        const free = form.querySelector('[data-family="' + c.dataset.path + '"]');
        free.hidden = !!known; free.value = v;
      } else c.value = v;
    });
    form.querySelectorAll('[data-num]').forEach((c) => { c.value = Math.round(get(work, c.dataset.num) * Number(c.dataset.k) * 100) / 100; });
    form.querySelectorAll('[data-hex]').forEach((c) => { c.value = get(work, c.dataset.hex); });
    form.querySelectorAll('[data-group]').forEach((g) => {
      const v = get(work, g.dataset.group);
      g.querySelectorAll('input').forEach((box) => { box.checked = g.dataset.group === 'chat.platforms' ? T.shows(v, box.value) : !!v[box.value]; });
    });
    whens();
  }

  function whens() {                               // fields that only matter when another one is set
    SECTIONS.forEach((s) => s.fields.filter((f) => f.when).forEach((f) => {
      const wrap = $('controls').querySelector('[data-when="' + f.path + '"]');
      const on = f.when(work);
      wrap.setAttribute('aria-disabled', String(!on));
      wrap.querySelectorAll('input, select').forEach((c) => { c.disabled = !on; });
    }));
  }

  function onInput(e) {
    const c = e.target;
    if (c.dataset.path) {
      const path = c.dataset.path, k = Number(c.dataset.k || 1);
      let v;
      if (c.type === 'checkbox') v = c.checked;
      else if (c.type === 'range') v = Number(c.value) / k;
      else if (c.dataset.kind === 'weight') v = Number(c.value);
      else if (c.dataset.kind === 'font') {
        const free = $('controls').querySelector('[data-family="' + path + '"]');
        free.hidden = c.value !== 'custom';
        if (c.value === 'custom') { free.focus(); return; }
        v = c.value;
      } else v = c.value;
      put(work, path, v);
      const num = $('controls').querySelector('[data-num="' + path + '"]'); if (num) num.value = Math.round(v * k * 100) / 100;
      const hex = $('controls').querySelector('[data-hex="' + path + '"]'); if (hex) hex.value = v;
    } else if (c.dataset.num) {
      const k = Number(c.dataset.k), v = Number(c.value) / k;
      if (c.value === '' || !isFinite(v)) return;
      put(work, c.dataset.num, v); $(idFor(c.dataset.num)).value = c.value;
    } else if (c.dataset.hex) {
      const v = T.color(c.value); if (!v) return;
      put(work, c.dataset.hex, v); $(idFor(c.dataset.hex)).value = v;
    } else if (c.dataset.family) {
      if (!c.value.trim()) return;
      put(work, c.dataset.family, c.value);
    } else if (c.closest('[data-group]')) {
      const g = c.closest('[data-group]'), on = [...g.querySelectorAll('input:checked')].map((b) => b.value);
      if (g.dataset.group === 'chat.platforms') work.chat.platforms = T.platforms(on.length ? on : T.PLATFORMS);
      else T.ALERTS.forEach((n) => { work.alerts.types[n] = on.includes(n); });
    } else return;
    changed();
  }

  function changed() {
    work = T.merge(work);                          // keep it valid: clamps numbers, drops bad colours
    whens();
    setDirty(JSON.stringify(work) !== saved);
    clearTimeout(pushTimer);
    pushTimer = setTimeout(push, 60);
  }

  function setDirty(on) {
    dirty = on;
    const d = $('dirty');
    d.className = on ? 'on' : '';
    d.textContent = on ? (current.builtin ? 'Changed (built-in themes are saved as a copy)' : current.name ? 'Unsaved changes' : 'New theme, not saved yet') : 'No changes';
    $('revert').disabled = !on || !current.name;
    $('save').textContent = current.builtin || !current.name ? 'Save as copy…' : 'Save';
    $('save').disabled = !on && !!current.name;
  }

  // ---- preview ------------------------------------------------------------------------------------------------
  function push() {
    Object.values(frames).forEach((f) => { if (f.contentWindow) f.contentWindow.postMessage({ crosschat: 'theme', theme: work }, location.origin); });
  }

  function stageSetup() {
    const stage = $('stage');
    Object.entries(WIDGETS).forEach(([w, info]) => {
      const zone = el('div', { class: 'zone', 'data-zone': w }, el('span', { text: info.label }));
      const frame = el('iframe', { title: info.label + ' preview', src: '/overlay/' + w + '?preview', tabIndex: -1, loading: 'eager' });
      frame.addEventListener('load', push);
      frames[w] = frame;
      stage.append(zone, frame);
    });
    window.addEventListener('message', (e) => { if (e.origin === location.origin && e.data && e.data.crosschat === 'ready') push(); });
    new ResizeObserver(layout).observe($('stage-wrap'));
    $('view').addEventListener('change', layout);
    $('back').addEventListener('change', () => {
      if ($('back').value === 'image') { $('back-file').click(); return; }
      stage.style.backgroundImage = ''; stage.dataset.back = $('back').value;
    });
    $('back-file').addEventListener('change', () => {
      const file = $('back-file').files[0];
      if (!file) { $('back').value = stage.dataset.back || 'game'; return; }
      if (backUrl) URL.revokeObjectURL(backUrl);
      backUrl = URL.createObjectURL(file);
      stage.dataset.back = 'image'; stage.style.backgroundImage = 'url("' + backUrl + '")';
    });
    layout();
  }

  function layout() {
    const view = $('view').value, wrap = $('stage-wrap'), stage = $('stage');
    const whole = view === 'stream';
    const [sw, sh] = whole ? [1920, 1080] : WIDGETS[view].size.map((n, i) => n + (i === 0 ? 120 : 80));
    Object.entries(WIDGETS).forEach(([w, info]) => {
      const on = whole || w === view, [x, y] = whole ? info.at : [60, 40], [fw, fh] = info.size;
      [frames[w], stage.querySelector('[data-zone="' + w + '"]')].forEach((n) => {
        n.style.display = on ? '' : 'none';
        Object.assign(n.style, { left: x + 'px', top: y + 'px', width: fw + 'px', height: fh + 'px' });
      });
    });
    const k = Math.min(1, wrap.clientWidth / sw);
    stage.style.width = sw + 'px'; stage.style.height = sh + 'px';
    stage.style.transform = 'scale(' + k + ')';
    wrap.style.height = Math.round(sh * k) + 'px';
  }

  function cards() {
    const box = $('widgets');
    Object.entries(WIDGETS).forEach(([w, info]) => {
      box.append(el('div', { class: 'card' },
        el('h3', { text: info.label }),
        el('span', { class: 'size', text: 'Browser Source ' + info.size[0] + ' × ' + info.size[1] }),
        el('span', { class: 'help', text: info.help }),
        el('div', { class: 'row' },
          el('button', { class: 'btn small', type: 'button', text: 'Copy OBS address', onclick: () => copyUrl(w) }),
          el('button', { class: 'btn small', type: 'button', text: 'Send test to OBS', onclick: () => test(info.test, info.label) }))));
    });
  }

  async function copyUrl(w) {
    if (!current.name) { say('Save this theme first: OBS can only use saved themes.', 'bad'); return; }
    const url = location.origin + '/overlay/' + w + '?theme=' + encodeURIComponent(current.name);
    try { await navigator.clipboard.writeText(url); say('Copied ' + url + (dirty ? ' (save to send your latest changes to OBS)' : ''), 'ok'); }
    catch (e) { say(url, 'ok'); }
  }

  async function test(kind, label) {
    try { await call('/test', { kind }); say('Sent a test to ' + label + ' sources in OBS.', 'ok'); }
    catch (e) { say('Could not reach CrossChat: ' + e.message, 'bad'); }
  }

  // ---- the theme list -----------------------------------------------------------------------------------------
  async function refresh(select) {
    try { list = await call('/themes'); } catch (e) { say('Could not load themes: ' + e.message, 'bad'); }
    const ul = $('themes');
    ul.replaceChildren(...list.themes.map((t) => {
      const meta = [t.builtin ? 'built-in' : t.name, t.name === list.default ? 'default' : ''].filter(Boolean).join(' · ');
      return el('li', {}, el('button', { type: 'button', 'aria-current': String(t.name === current.name), 'data-name': t.name, onclick: () => choose(t.name) },
        el('span', { class: 'label', text: t.label || t.name }), el('span', { class: 'meta', text: meta })));
    }));
    if (select) await choose(select, true);
    buttons();
  }

  function buttons() {
    const saved = !!current.name;
    $('delete').disabled = !saved || current.builtin;
    $('make-default').disabled = !saved || current.name === list.default;
    $('themes').querySelectorAll('button').forEach((b) => b.setAttribute('aria-current', String(b.dataset.name === current.name)));
  }

  async function leaveOk() {
    return !dirty || ask('Discard changes?', 'Your changes to “' + work.label + '” are not saved.', 'Discard');
  }

  async function choose(name, force) {
    if (!force && !(await leaveOk())) return;
    try {
      const raw = await call('/themes/' + encodeURIComponent(name));
      const info = list.themes.find((t) => t.name === name) || { builtin: false };
      load(T.merge(raw), { name, builtin: !!info.builtin });
    } catch (e) { say('Could not open ' + name + ': ' + e.message, 'bad'); }
  }

  function load(theme, who) {
    work = theme; current = who; saved = who.name ? JSON.stringify(theme) : '';
    fill(); setDirty(!who.name); buttons(); push();
  }

  // ---- saving ---------------------------------------------------------------------------------------------------
  async function save(name, label) {
    const theme = T.merge({ ...work, label });
    const answer = await call('/themes/save', { name, theme });
    if (!answer.ok) throw new Error(answer.why || 'not saved');
    work = theme; current = { name, builtin: false }; saved = JSON.stringify(work);
    setDirty(false);
    await refresh();
    fill();
    say('Saved “' + label + '”. OBS sources using ?theme=' + name + ' update now.', 'ok');
  }

  function saveAs() {
    const d = $('save-dialog'), label = $('save-label'), name = $('save-name'), error = $('save-error');
    const suggested = current.builtin ? work.label + ' (my copy)' : work.label;
    label.value = suggested; name.value = T.slug(suggested); error.textContent = '';
    let typed = false;
    label.oninput = () => { if (!typed) name.value = T.slug(label.value); };
    name.oninput = () => { typed = true; };
    d.returnValue = ''; d.showModal(); label.select();
    $('save-form').onsubmit = async (e) => {
      if (e.submitter && e.submitter.value === 'cancel') return;
      e.preventDefault();
      const n = name.value.trim(), l = label.value.trim() || n;
      if (!T.validName(n)) { error.textContent = 'Use lowercase letters, numbers and dashes, starting with a letter or number.'; name.focus(); return; }
      const clash = list.themes.find((t) => t.name === n);
      if (clash && clash.builtin) { error.textContent = '“' + n + '” is a built-in theme. Pick another file name.'; name.focus(); return; }
      if (clash && n !== current.name && !(await ask('Replace “' + (clash.label || n) + '”?', 'A theme with the file name ' + n + ' already exists.', 'Replace'))) return;
      try { await save(n, l); d.close('ok'); } catch (err) { error.textContent = err.message; }
    };
  }

  // ---- buttons --------------------------------------------------------------------------------------------------
  function wire() {
    $('save').onclick = () => (current.builtin || !current.name ? saveAs() : save(current.name, work.label).catch((e) => say(e.message, 'bad')));
    $('save-as').onclick = saveAs;
    $('revert').onclick = async () => { if (current.name && (await ask('Revert?', 'Go back to the saved “' + work.label + '”.', 'Revert'))) choose(current.name, true); };
    $('new').onclick = async () => { if (await leaveOk()) load(T.merge({ label: 'My theme' }), { name: null, builtin: false }); };
    $('duplicate').onclick = async () => { const copy = T.merge({ ...work, label: (work.label + ' copy').slice(0, 60) }); load(copy, { name: null, builtin: false }); setDirty(true); };
    $('import').onclick = () => $('import-file').click();
    $('import-file').onchange = async () => {
      const file = $('import-file').files[0]; $('import-file').value = '';
      if (!file || !(await leaveOk())) return;
      try {
        if (file.size > 64 * 1024) throw new Error('the file is bigger than 64 KB');
        const raw = JSON.parse(await file.text()), issues = T.problems(raw);
        load(T.merge(raw), { name: null, builtin: false });
        say('Imported “' + work.label + '”' + (issues.length ? ' with ' + issues.length + ' fix(es): ' + issues.slice(0, 2).join('; ') : '') + '. Save it to use it in OBS.', issues.length ? 'bad' : 'ok');
      } catch (e) { say('Could not import that file: ' + e.message, 'bad'); }
    };
    $('export').onclick = () => {
      const blob = new Blob([JSON.stringify(work, null, 2) + '\n'], { type: 'application/json' });
      const a = el('a', { href: URL.createObjectURL(blob), download: (current.name || T.slug(work.label)) + '.json' });
      doc.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      say('Exported ' + a.download + '. Share it, or import it on another PC.', 'ok');
    };
    $('delete').onclick = async () => {
      if (!current.name || current.builtin || !(await ask('Delete “' + work.label + '”?', 'OBS sources using it go back to the default theme.', 'Delete'))) return;
      try {
        const answer = await call('/themes/delete', { name: current.name });
        if (!answer.ok) throw new Error(answer.why || 'not deleted');
        dirty = false; current = { name: null, builtin: false };
        await refresh(list.default);
        say('Deleted.', 'ok');
      } catch (e) { say(e.message, 'bad'); }
    };
    $('make-default').onclick = async () => {
      try {
        const answer = await call('/themes/default', { name: current.name });
        if (!answer.ok) throw new Error(answer.why || 'not changed');
        await refresh(); say('“' + work.label + '” is now the default: sources without ?theme= use it.', 'ok');
      } catch (e) { say(e.message, 'bad'); }
    };
    window.addEventListener('beforeunload', (e) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });

    const modes = { auto: ['◐', 'Studio look: follows Windows'], light: ['☀', 'Studio look: light'], dark: ['☾', 'Studio look: dark'] };
    const showMode = () => { const m = doc.documentElement.dataset.theme || 'auto'; $('mode').textContent = modes[m][0]; $('mode').title = modes[m][1]; $('mode').setAttribute('aria-label', modes[m][1] + ' (change)'); };
    $('mode').onclick = () => {
      const order = ['auto', 'light', 'dark'], next = order[(order.indexOf(doc.documentElement.dataset.theme || 'auto') + 1) % 3];
      if (next === 'auto') delete doc.documentElement.dataset.theme; else doc.documentElement.dataset.theme = next;
      try { localStorage.setItem('theme', next); } catch (e) { /* not kept: fine */ }
      showMode();
    };
    showMode();
  }

  build(); cards(); stageSetup(); wire();
  const wanted = new URLSearchParams(location.search).get('theme');
  refresh().then(() => choose(T.validName(wanted) ? wanted : list.default, true));
})();
