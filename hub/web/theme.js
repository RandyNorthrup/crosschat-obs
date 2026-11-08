// CrossChat themes: what a theme may contain, how a theme file is checked and filled in, and how it turns into
// CSS custom properties (--cc-*) and data-* switches on the page. Used by the overlays, the Theme Studio and the
// tests (Node loads this file too, so nothing here may touch the page unless it is handed a document).
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.CrossChatTheme = api;
})(typeof self !== 'undefined' ? self : globalThis, function () {
  const SCHEMA = 1;
  const PLATFORMS = ['twitch', 'youtube', 'kick', 'x', 'tiktok', 'facebook', 'instagram', 'rumble'];
  // Alert types. YouTube's Super Stickers and Rumble's Rants come from the hub as "superchat" and are told apart by
  // alertKind(), so each can have its own sentence and switch.
  const ALERTS = ['sub', 'resub', 'gift', 'raid', 'cheer', 'member', 'superchat', 'sticker', 'rant', 'follow', 'share', 'like', 'join', 'other'];
  // Too many on a busy stream to pop up or fill the on-stream chat unless the theme turns them on.
  const QUIET_ALERTS = ['like', 'join'];
  const SANS = '"Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif';
  // Custom logos and names: one for every platform ("all") and one per platform. Per platform beats "all", "all" beats built-in.
  const LOGO_KEYS = ['all', ...PLATFORMS];
  const BUBBLE = 'chat';                           // a logo value: CrossChat's plain speech bubble instead of a brand
  const NO_NAME = '-';                             // a name value: show no name at all
  const LOGO_MOST = 20000;                         // characters of one logo in a theme file
  const LOGO_BOXES = [128, 96, 64, 48];            // the square sizes the Theme Studio tries, biggest first
  const THEME_MOST = 224 * 1024;                   // bytes of a theme file with all nine logos; hub.py keeps the same limit
  const blanks = () => Object.fromEntries(LOGO_KEYS.map((k) => [k, '']));

  // Every key a theme may have, with its default. A theme file only needs the keys it changes.
  const DEFAULTS = {
    schema: SCHEMA,
    label: 'Untitled',
    font: { family: SANS, google: '', size: 20, weight: 500, nameWeight: 700, lineHeight: 1.35 },
    colors: {
      text: '#f3eee6',
      name: 'user',                // platform | user (the viewer's own colour, kept legible) | fixed
      nameColor: '#e3a57b',
      background: '#0d141c',
      backgroundOpacity: 0.84,
      accent: '#b87045',
      outline: '#000000',
      outlineWidth: 0,
      shadow: 0.35,
      twitch: '#9146ff',
      youtube: '#ff0033',
      kick: '#53fc18',
      x: '#e7e9ea',
      tiktok: '#fe2c55',
      facebook: '#0866ff',
      instagram: '#ff0069',
      rumble: '#85c742',
    },
    message: {
      layout: 'card',              // card | bubble | line | compact
      radius: 12,
      padding: 12,
      gap: 8,
      accentBar: true,
      accentWidth: 3,
      platform: 'icon',            // icon | text | bar | none
      badges: true,
      emoteSize: 28,
      timestamps: false,
      firstHighlight: true,        // a viewer's first message in the channel ever: highlighted, with a NEW tag
    },
    chat: {
      direction: 'bottom',         // bottom: newest at the bottom | top: newest at the top
      align: 'left',
      max: 9,
      seconds: 120,                // 0: messages stay
      animationIn: 'slide',        // slide | fade | pop | none
      animationOut: 'fade',        // fade | slide | none
      platforms: 'all',            // "all" or a list such as ["twitch", "youtube"]
      events: true,                // subs, raids and the like as highlighted lines in the chat too
      delay: 0,                    // seconds each message waits before it shows; deleted or hidden meanwhile, it never does
    },
    featured: { layout: 'card', scale: 1.5, platform: true, seconds: 0, animation: 'pop' },
    viewers: { layout: 'row', perPlatform: true, label: 'watching', icon: true },
    alerts: {
      seconds: 7,
      animation: 'pop',
      sound: true,
      volume: 0.35,
      showText: true,
      types: { sub: true, resub: true, gift: true, raid: true, cheer: true, member: true, superchat: true, sticker: true, rant: true, follow: true,
               share: true, like: false, join: false, other: true },
      labels: {
        sub: '{name} just subscribed!',
        resub: '{name} resubscribed for {amount} months!',
        gift: '{name} gifted {amount}!',
        raid: '{name} is raiding with {amount} viewers!',
        cheer: '{name} cheered {amount}!',
        member: '{name} became a member!',
        superchat: '{name} sent a Super Chat: {amount}',
        sticker: '{name} sent a Super Sticker: {amount}',
        rant: '{name} sent a Rant: {amount}',
        follow: '{name} followed!',
        share: '{name} shared the LIVE!',
        like: '{name} liked the LIVE ×{amount}',
        join: '{name} joined',
        other: '{text}',
      },
    },
    logos: blanks(),               // '' built-in | 'chat' the plain bubble | a small picture (data:image/png, webp or jpeg)
    names: blanks(),               // '' built-in | your own name | '-' no name
    css: '',
  };

  // Numbers: [lowest, highest, step].
  const RANGES = {
    'font.size': [10, 72, 1], 'font.weight': [100, 900, 100], 'font.nameWeight': [100, 900, 100], 'font.lineHeight': [1, 2, 0.05],
    'colors.backgroundOpacity': [0, 1, 0.01], 'colors.outlineWidth': [0, 6, 0.5], 'colors.shadow': [0, 1, 0.05],
    'message.radius': [0, 40, 1], 'message.padding': [0, 40, 1], 'message.gap': [0, 40, 1], 'message.accentWidth': [0, 12, 1],
    'message.emoteSize': [12, 64, 1],
    'chat.max': [1, 50, 1], 'chat.seconds': [0, 3600, 1], 'chat.delay': [0, 60, 1],
    'featured.scale': [0.5, 3, 0.05], 'featured.seconds': [0, 600, 1],
    'alerts.seconds': [1, 60, 0.5], 'alerts.volume': [0, 1, 0.05],
  };

  const ENUMS = {
    'colors.name': ['platform', 'user', 'fixed'],
    'message.layout': ['card', 'bubble', 'line', 'compact'],
    'message.platform': ['icon', 'text', 'bar', 'none'],
    'chat.direction': ['bottom', 'top'],
    'chat.align': ['left', 'right'],
    'chat.animationIn': ['slide', 'fade', 'pop', 'none'],
    'chat.animationOut': ['fade', 'slide', 'none'],
    'featured.layout': ['card', 'banner'],
    'featured.animation': ['pop', 'slide', 'fade', 'none'],
    'viewers.layout': ['row', 'stack', 'total'],
    'alerts.animation': ['pop', 'slide', 'fade', 'none'],
  };

  // Free text: longest allowed, and the characters allowed where it matters.
  const TEXTS = {
    label: [60], 'font.family': [200, /^[A-Za-z0-9 ,"'-]+$/], 'font.google': [40, /^[A-Za-z0-9 ]*$/],
    'viewers.label': [40], css: [20000],
  };
  LOGO_KEYS.forEach((k) => { TEXTS['names.' + k] = [24]; });

  const clone = (v) => JSON.parse(JSON.stringify(v));
  const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

  function color(value) {
    if (typeof value !== 'string') return null;
    const v = value.trim().toLowerCase();
    if (/^#[0-9a-f]{6}$/.test(v)) return v;
    if (/^#[0-9a-f]{3}$/.test(v)) return '#' + [...v.slice(1)].map((c) => c + c).join('');
    return null;
  }

  function number(value, path, issues) {
    const n = typeof value === 'string' && value.trim() !== '' ? Number(value) : value;
    if (typeof n !== 'number' || !isFinite(n)) { issues.push(path + ': not a number'); return undefined; }
    const [lo, hi, step] = RANGES[path] || [-Infinity, Infinity, 0];
    let out = Math.min(hi, Math.max(lo, n));
    if (step) out = Math.round(Math.round((out - lo) / step) * step * 1000 + lo * 1000) / 1000;
    if (out !== n) issues.push(path + ': ' + n + ' adjusted to ' + out);
    return out;
  }

  function platforms(value) {
    if (value === 'all' || value == null || value === '') return 'all';
    const list = (Array.isArray(value) ? value : String(value).split(','))
      .map((p) => String(p).trim().toLowerCase()).filter((p) => PLATFORMS.includes(p));
    const unique = [...new Set(list)];
    return unique.length === 0 || unique.length === PLATFORMS.length ? 'all' : unique;
  }

  // A logo as a theme file may hold it, or null. Only small pictures of these types: never SVG (which can carry
  // scripts) and never an address (which would tell another server the streamer's IP each time the overlay loads).
  function logo(value) {
    if (value === '' || value === BUBBLE) return value;
    return typeof value === 'string' && value.length <= LOGO_MOST && /^data:image\/(png|webp|jpeg);base64,[A-Za-z0-9+/]+={0,2}$/.test(value) ? value : null;
  }

  // Lay `input` over `base` (a slice of DEFAULTS), keeping only known keys with usable values.
  function walk(base, input, path, issues) {
    const out = clone(base);
    if (!isObject(input)) return out;
    for (const key of Object.keys(input)) {
      const at = path ? path + '.' + key : key;
      if (!(key in base)) { issues.push(at + ': unknown key, ignored'); continue; }
      const want = base[key], value = input[key];
      if (at === 'chat.platforms') { out[key] = platforms(value); continue; }
      if (at === 'schema') continue;
      if (path === 'logos') {
        const picture = logo(value);
        if (picture === null) issues.push(at + ': not a small PNG, WebP or JPEG picture'); else out[key] = picture;
        continue;
      }
      if (isObject(want)) { out[key] = walk(want, value, at, issues); continue; }
      if (typeof want === 'boolean') {
        if (typeof value === 'boolean') out[key] = value; else issues.push(at + ': not true or false');
      } else if (typeof want === 'number') {
        const n = number(value, at, issues);
        if (n !== undefined) out[key] = n;
      } else if (path === 'colors' && /^#/.test(want)) {
        const c = color(value);
        if (c) out[key] = c; else issues.push(at + ': not a colour like #1a2b3c');
      } else if (ENUMS[at]) {
        if (ENUMS[at].includes(value)) out[key] = value; else issues.push(at + ': must be one of ' + ENUMS[at].join(', '));
      } else if (typeof value === 'string') {
        const [longest, allowed] = TEXTS[at] || [140];
        const text = value.slice(0, longest);
        if (text.length < value.length) issues.push(at + ': cut to ' + longest + ' characters');
        if (allowed && !allowed.test(text)) issues.push(at + ': has characters that are not allowed');
        else out[key] = text;
      } else {
        issues.push(at + ': not text');
      }
    }
    return out;
  }

  // A complete, safe theme from whatever a theme file holds (missing keys come from DEFAULTS).
  function merge(theme, over) {
    const issues = [];
    let out = walk(DEFAULTS, theme, '', issues);
    if (over) out = walk(out, over, '', issues);
    out.schema = SCHEMA;
    return out;
  }

  // What is wrong with a theme file, as plain sentences ([] when nothing is).
  function problems(theme) {
    const issues = [];
    if (!isObject(theme)) return ['the theme is not a JSON object'];
    if (theme.schema !== undefined && theme.schema !== SCHEMA) issues.push('schema: ' + theme.schema + ' is not ' + SCHEMA);
    walk(DEFAULTS, theme, '', issues);
    return issues;
  }

  const validName = (name) => typeof name === 'string' && /^[a-z0-9][a-z0-9-]{0,39}$/.test(name);
  const slug = (text) => String(text || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'my-theme';

  function rgb(hex) { const c = color(hex) || '#000000'; return [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16)); }
  function luminance(hex) {
    const [r, g, b] = rgb(hex).map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }
  const contrast = (a, b) => { const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const hex = (r, g, b) => '#' + [r, g, b].map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('');

  // Does this theme put text on a light surface? (Then emotes use their light versions and colours darken.)
  const lightSurface = (t) => t.colors.backgroundOpacity >= 0.5 && luminance(t.colors.background) > 0.45;

  // A viewer-chosen colour moved until it reads well on the theme's surface (at least 3:1, like large text).
  function readable(value, t) {
    const c = color(value);
    if (!c) return null;
    if (t.colors.backgroundOpacity < 0.35) return c;          // no surface: the outline does the work
    const bg = t.colors.background, light = luminance(bg) > 0.45;
    let [r, g, b] = rgb(c), out = c;
    for (let i = 0; i < 12 && contrast(out, bg) < 3; i++) {
      [r, g, b] = light ? [r * 0.85, g * 0.85, b * 0.85] : [r + (255 - r) * 0.18, g + (255 - g) * 0.18, b + (255 - b) * 0.18];
      out = hex(r, g, b);
    }
    return out;
  }

  // Black or white, whichever reads better on `bg`.
  const ink = (bg) => (contrast('#000000', bg) >= contrast('#ffffff', bg) ? '#0b0f14' : '#ffffff');

  function nameColor(m, t) {
    const own = t.colors[m.p] || t.colors.accent;
    if (t.colors.name === 'fixed') return t.colors.nameColor;
    if (t.colors.name === 'platform') return readable(own, t) || own;
    return readable(m.color, t) || readable(own, t) || own;
  }

  // The platforms a chat overlay shows: ?platforms= wins, then the theme's own list, then overlay.platforms in config.json.
  // Returns "all" or a list.
  function wanted(themePlatforms, param, configured) {
    if (param != null && param !== '') return platforms(param);
    const own = platforms(themePlatforms);
    return own !== 'all' ? own : platforms(configured);
  }
  const shows = (list, p) => list === 'all' || list.includes(p);

  const known = (map, p) => (PLATFORMS.includes(p) ? String(map[p] || '').trim() : '');
  const customName = (t, p) => known(t.names, p) || (PLATFORMS.includes(p) ? String(t.names.all || '').trim() : '');

  // The logo theme t puts on platform p: a picture, BUBBLE, or '' for the platform's own glyph.
  const logoFor = (t, p) => known(t.logos, p) || (PLATFORMS.includes(p) ? t.logos.all : '') || '';

  // The name theme t shows for platform p: its own, or `builtin` when it sets none, or '' when it hides names.
  function platformName(t, p, builtin) {
    const name = customName(t, p);
    if (!name) return builtin || '';
    return name === NO_NAME ? '' : name;
  }

  // The short tag ("TW") for the text style: `builtin` unless the theme renames or hides the platform.
  function platformTag(t, p, builtin) {
    const name = customName(t, p);
    if (!name) return builtin;
    return name === NO_NAME ? '•' : [...name].slice(0, 3).join('').toUpperCase();
  }

  // The biggest rendering of a picture that fits in a theme, or '' when none does. render(box, type) gives a data URL.
  function shrinkLogo(render) {
    for (const box of LOGO_BOXES) {
      for (const type of ['image/png', 'image/webp']) {
        const url = render(box, type);
        if (logo(url)) return url;
      }
    }
    return '';
  }

  // Where a picture of this size goes in a square: whole, centred.
  function logoBox(width, height, box) {
    const k = box / Math.max(width, height, 1), w = Math.max(1, Math.round(width * k)), h = Math.max(1, Math.round(height * k));
    return { x: Math.floor((box - w) / 2), y: Math.floor((box - h) / 2), w, h };
  }

  // A message split into text and Twitch emotes. Twitch counts positions in code points, so this does too.
  function emotePieces(text, emotes) {
    const chars = [...String(text || '')], ranges = [];
    String(emotes || '').split('/').filter(Boolean).forEach((e) => {
      const [id, spots] = e.split(':');
      (spots || '').split(',').forEach((s) => { const [a, z] = s.split('-').map(Number); ranges.push([a, z, id]); });
    });
    const out = [];
    let at = 0;
    ranges.sort((p, q) => p[0] - q[0]).forEach(([a, z, id]) => {
      if (!/^\w+$/.test(id || '') || !(a >= at && z >= a && z < chars.length)) return;
      if (a > at) out.push({ text: chars.slice(at, a).join('') });
      out.push({ emote: id, alt: chars.slice(a, z + 1).join('') });
      at = z + 1;
    });
    if (at < chars.length) out.push({ text: chars.slice(at).join('') });
    return out;
  }

  // "{name} gifted {amount}" filled in, as pieces: [{text}] and [{key, value}] for the filled-in words, so a page can
  // style them. Unknown {words} are left out.
  function fillParts(template, vars) {
    const out = [];
    String(template || '').split(/(\{\w+\})/).forEach((bit) => {
      const key = (/^\{(\w+)\}$/.exec(bit) || [])[1];
      if (key && vars[key] != null && String(vars[key]) !== '') out.push({ key, value: String(vars[key]) });
      else if (bit && !key) out.push({ text: bit });
    });
    while (out.length && out[out.length - 1].text !== undefined && !out[out.length - 1].text.trim()) out.pop();
    return out;
  }

  // ---- alerts: one look for every platform's subs, gifts, raids, cheers, Super Chats and Rants ------------------------
  // An event's alert type. Unknown types (a platform adding something new) are "other".
  function alertKind(m) {
    const a = m && m.alert;
    if (a === 'superchat' && m.p === 'rumble') return 'rant';
    if (a === 'superchat' && m.p === 'youtube' && /^super sticker/i.test(m.system || '')) return 'sticker';
    return ALERTS.includes(a) ? a : 'other';
  }

  // The built-in sentences for when the platform sent no amount (a resub without its months, say).
  const BARE = { resub: '{name} resubscribed!', gift: '{name} sent a gift!', raid: '{name} is raiding!', cheer: '{name} cheered!',
                 superchat: '{name} sent a Super Chat!', sticker: '{name} sent a Super Sticker!', rant: '{name} sent a Rant!' };
  const oneLine = (v) => String(v == null ? '' : v).replace(/\s+/g, ' ').trim();

  // Neighbouring text pieces joined, with no doubled or dangling spaces where a missing value was left out.
  function tidy(parts) {
    const out = [];
    parts.forEach((p) => {
      const last = out[out.length - 1];
      if (p.text !== undefined && last && last.text !== undefined) last.text += p.text; else out.push({ ...p });
    });
    out.forEach((p, i) => {
      if (p.text === undefined) return;
      p.text = p.text.replace(/\s+/g, ' ');
      if (i === 0) p.text = p.text.trimStart();
      if (i === out.length - 1) p.text = p.text.trimEnd();
    });
    return out.filter((p) => p.text !== '');
  }

  // An alert's title for theme t, as pieces ([{text}] and [{key, value}]) a page can style: the theme's sentence for
  // its type, a shorter built-in one when the amount is missing, and the platform's own sentence (or the name) when
  // nothing readable is left. words: whether the viewer's own message goes under (or after) the title.
  function alertParts(m, t, platform) {
    m = m || {};
    const kind = alertKind(m), labels = (t && t.alerts && t.alerts.labels) || DEFAULTS.alerts.labels;
    let template = typeof labels[kind] === 'string' ? labels[kind] : DEFAULTS.alerts.labels[kind];
    const vars = { name: oneLine(m.name) || 'Someone', amount: oneLine(m.amount), text: oneLine(m.text), platform: platform || '' };
    if (!vars.amount && template === DEFAULTS.alerts.labels[kind] && BARE[kind]) template = BARE[kind];
    const own = oneLine(m.system);
    if (kind === 'other' && template === DEFAULTS.alerts.labels.other && own && !vars.text.includes(own)) {
      return { kind, parts: [{ text: own }], words: !!vars.text };     // an event type CrossChat doesn't know: the platform's words
    }
    const parts = tidy(fillParts(template, vars));
    if (parts.some((p) => /[\p{L}\p{N}]/u.test(p.text !== undefined ? p.text : p.value))) {
      return { kind, parts, words: !!vars.text && !/\{text\}/.test(template) };
    }
    const title = own || vars.text || vars.name;
    return { kind, parts: [{ text: title }], words: !!vars.text && vars.text !== title };
  }

  // The same as one line of text, the viewer's message after a dot: for the chat feed and the chat window.
  function alertLine(m, t, platform) {
    const a = alertParts(m, t, platform);
    const title = a.parts.map((p) => (p.text !== undefined ? p.text : p.value)).join('');
    return a.words ? title + ' · ' + oneLine(m.text) : title;
  }

  function outlineShadow(t) {
    const w = t.colors.outlineWidth;
    if (!w) return 'none';
    const c = t.colors.outline, d = Math.round(w * 0.7 * 100) / 100, out = [];
    [[w, 0], [-w, 0], [0, w], [0, -w], [d, d], [-d, d], [d, -d], [-d, -d]].forEach(([x, y]) => out.push(x + 'px ' + y + 'px 0 ' + c));
    out.push('0 0 ' + (w * 2) + 'px ' + c);
    return out.join(', ');
  }

  function fontStack(t) {
    const google = (t.font.google || '').trim();
    return google ? '"' + google + '", ' + t.font.family : t.font.family;
  }

  // The CSS custom properties a theme sets. Documented in docs/THEMES.md; OBS's Custom CSS can use them.
  function cssVars(t) {
    const [r, g, b] = rgb(t.colors.background), s = t.colors.shadow;
    const vars = {
      '--cc-font': fontStack(t),
      '--cc-size': t.font.size + 'px',
      '--cc-weight': String(t.font.weight),
      '--cc-name-weight': String(t.font.nameWeight),
      '--cc-line': String(t.font.lineHeight),
      '--cc-text': t.colors.text,
      '--cc-name-fixed': t.colors.nameColor,
      '--cc-bg': 'rgba(' + r + ', ' + g + ', ' + b + ', ' + t.colors.backgroundOpacity + ')',
      '--cc-bg-solid': t.colors.background,
      '--cc-accent': t.colors.accent,
      '--cc-accent-ink': ink(t.colors.accent),
      '--cc-outline': t.colors.outline,
      '--cc-text-shadow': outlineShadow(t),
      '--cc-icon-filter': t.colors.outlineWidth ? 'drop-shadow(0 0 ' + t.colors.outlineWidth * 0.6 + 'px ' + t.colors.outline + ') drop-shadow(0 0 '
        + t.colors.outlineWidth * 0.6 + 'px ' + t.colors.outline + ')' : 'none',
      '--cc-shadow': s ? '0 ' + Math.round(3 + 9 * s) + 'px ' + Math.round(10 + 22 * s) + 'px rgba(0, 0, 0, ' + (0.12 + 0.45 * s).toFixed(2) + ')' : 'none',
      '--cc-radius': t.message.radius + 'px',
      '--cc-pad': t.message.padding + 'px',
      '--cc-gap': t.message.gap + 'px',
      '--cc-bar': (t.message.platform === 'bar' ? Math.max(t.message.accentWidth, 3) : t.message.accentBar ? t.message.accentWidth : 0) + 'px',
      '--cc-emote': t.message.emoteSize + 'px',
      '--cc-featured-scale': String(t.featured.scale),
      '--cc-alert-seconds': t.alerts.seconds + 's',
    };
    PLATFORMS.forEach((p) => { vars['--cc-' + p] = t.colors[p]; });
    return vars;
  }

  // The data-* switches the overlay CSS keys off.
  function switches(t) {
    return {
      layout: t.message.layout, platformStyle: t.message.platform, badges: String(t.message.badges), timestamps: String(t.message.timestamps),
      direction: t.chat.direction, align: t.chat.align, in: t.chat.animationIn, out: t.chat.animationOut,
      featured: t.featured.layout, featuredIn: t.featured.animation, viewers: t.viewers.layout, alertIn: t.alerts.animation,
      surface: lightSurface(t) ? 'light' : 'dark',
    };
  }

  // Put a complete theme on a page: variables, switches, its Google Font and its custom CSS.
  function apply(t, doc) {
    const root = doc.documentElement;
    Object.entries(cssVars(t)).forEach(([k, v]) => root.style.setProperty(k, v));
    Object.entries(switches(t)).forEach(([k, v]) => { root.dataset[k] = v; });
    let link = doc.getElementById('cc-google-font');
    const google = (t.font.google || '').trim();
    if (google) {
      const href = 'https://fonts.googleapis.com/css2?family=' + encodeURIComponent(google).replace(/%20/g, '+') + ':wght@300;400;500;600;700;800;900&display=swap';
      if (!link) { link = doc.createElement('link'); link.id = 'cc-google-font'; link.rel = 'stylesheet'; doc.head.appendChild(link); }
      if (link.getAttribute('href') !== href) link.setAttribute('href', href);
    } else if (link) link.remove();
    let style = doc.getElementById('cc-custom-css');
    if (!style) { style = doc.createElement('style'); style.id = 'cc-custom-css'; doc.head.appendChild(style); }
    style.textContent = t.css || '';
  }

  return {
    SCHEMA, PLATFORMS, ALERTS, QUIET_ALERTS, DEFAULTS, RANGES, ENUMS, TEXTS, LOGO_KEYS, BUBBLE, NO_NAME, LOGO_MOST, THEME_MOST,
    logoFor, platformName, platformTag, shrinkLogo, logoBox,
    merge, problems, validName, slug, color, platforms, wanted, shows, emotePieces, fillParts,
    alertKind, alertParts, alertLine,
    luminance, contrast, readable, ink, nameColor, lightSurface, cssVars, switches, apply, clone,
  };
});
