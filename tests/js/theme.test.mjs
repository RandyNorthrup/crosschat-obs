// Tests for hub/web/theme.js and the built-in presets. Run: node --test tests/js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const T = require('../../hub/web/theme.js');
const I = require('../../hub/web/icons.js');
const A = require('../../hub/web/app.js');
const presetDir = path.join(here, '..', '..', 'hub', 'presets');

test('an empty theme is the defaults', () => {
  assert.deepEqual(T.merge({}), { ...T.DEFAULTS, schema: T.SCHEMA });
  assert.deepEqual(T.merge(null), T.merge({}));
  assert.deepEqual(T.problems({}), []);
});

test('numbers are clamped and stepped', () => {
  assert.equal(T.merge({ font: { size: 999 } }).font.size, 72);
  assert.equal(T.merge({ font: { size: 3 } }).font.size, 10);
  assert.equal(T.merge({ font: { size: '24' } }).font.size, 24);
  assert.equal(T.merge({ font: { lineHeight: 1.333 } }).font.lineHeight, 1.35);
  assert.equal(T.merge({ colors: { backgroundOpacity: 1.5 } }).colors.backgroundOpacity, 1);
  assert.equal(T.merge({ chat: { max: 0 } }).chat.max, 1);
  assert.equal(T.merge({ font: { size: 'big' } }).font.size, T.DEFAULTS.font.size);
  assert.match(T.problems({ font: { size: 999 } })[0], /adjusted to 72/);
});

test('colours must be hex', () => {
  assert.equal(T.merge({ colors: { text: '#ABC' } }).colors.text, '#aabbcc');
  assert.equal(T.merge({ colors: { text: '#A1B2C3' } }).colors.text, '#a1b2c3');
  assert.equal(T.merge({ colors: { text: 'red' } }).colors.text, T.DEFAULTS.colors.text);
  assert.equal(T.merge({ colors: { accent: 'url(x)' } }).colors.accent, T.DEFAULTS.colors.accent);
  assert.match(T.problems({ colors: { text: 'red' } })[0], /not a colour/);
});

test('unknown keys and wrong types are dropped and reported', () => {
  const t = T.merge({ bogus: 1, font: { nope: true }, message: { badges: 'yes' } });
  assert.equal('bogus' in t, false);
  assert.equal('nope' in t.font, false);
  assert.equal(t.message.badges, true);
  const issues = T.problems({ bogus: 1, font: { nope: true }, message: { badges: 'yes' } });
  assert.deepEqual(issues, ['bogus: unknown key, ignored', 'font.nope: unknown key, ignored', 'message.badges: not true or false']);
  assert.deepEqual(T.problems([]), ['the theme is not a JSON object']);
  assert.match(T.problems({ schema: 2 })[0], /schema/);
});

test('choices must be known values', () => {
  assert.equal(T.merge({ message: { layout: 'grid' } }).message.layout, 'card');
  assert.equal(T.merge({ message: { layout: 'bubble' } }).message.layout, 'bubble');
  assert.equal(T.merge({ colors: { name: 'fixed' } }).colors.name, 'fixed');
});

test('free text is limited and font names are sanitised', () => {
  assert.equal(T.merge({ font: { google: 'Inter' } }).font.google, 'Inter');
  assert.equal(T.merge({ font: { google: 'Inter; } body {' } }).font.google, '');
  assert.equal(T.merge({ font: { family: '"My Font", sans-serif' } }).font.family, '"My Font", sans-serif');
  assert.equal(T.merge({ font: { family: 'x; background: url(evil)' } }).font.family, T.DEFAULTS.font.family);
  assert.equal(T.merge({ label: 'x'.repeat(100) }).label.length, 60);
  assert.equal(T.merge({ css: '.cc-name { color: red; }' }).css, '.cc-name { color: red; }');
});

test('chat platform filter', () => {
  assert.equal(T.platforms('all'), 'all');
  assert.equal(T.platforms(''), 'all');
  assert.deepEqual(T.platforms('twitch, YouTube'), ['twitch', 'youtube']);
  assert.deepEqual(T.platforms(['x', 'x', 'kick']), ['x', 'kick']);
  assert.equal(T.platforms(['nothing']), 'all');
  assert.equal(T.platforms(['twitch', 'youtube', 'kick', 'x', 'tiktok', 'facebook', 'instagram', 'rumble']), 'all');
  assert.deepEqual(T.platforms(['instagram']), ['instagram']);
  assert.deepEqual(T.platforms(['tiktok', 'myspace']), ['tiktok']);
  assert.deepEqual(T.merge({ chat: { platforms: 'twitch' } }).chat.platforms, ['twitch']);
  // the address wins over the theme
  assert.deepEqual(T.wanted(['twitch'], 'youtube,x'), ['youtube', 'x']);
  assert.deepEqual(T.wanted(['twitch'], null), ['twitch']);
  assert.equal(T.wanted('all', ''), 'all');
  // then the theme's own list, then overlay.platforms in config.json
  assert.deepEqual(T.wanted('all', null, ['twitch']), ['twitch']);
  assert.deepEqual(T.wanted(['kick'], null, ['twitch']), ['kick']);
  assert.deepEqual(T.wanted(['kick'], 'youtube', ['twitch']), ['youtube']);
  assert.deepEqual(T.wanted('all', '', 'twitch'), ['twitch']);
  assert.equal(T.wanted('all', null, undefined), 'all');
  assert.equal(T.wanted('all', null, 'all'), 'all');
  assert.equal(T.shows('all', 'kick'), true);
  assert.equal(T.shows(['twitch'], 'kick'), false);
});

test('emote ranges count code points', () => {
  assert.deepEqual(T.emotePieces('👋 Kappa', '25:2-6'), [{ text: '👋 ' }, { emote: '25', alt: 'Kappa' }]);
  assert.deepEqual(T.emotePieces('Kappa hi Kappa', '25:0-4,9-13'),
    [{ emote: '25', alt: 'Kappa' }, { text: ' hi ' }, { emote: '25', alt: 'Kappa' }]);
  assert.deepEqual(T.emotePieces('a HeyGuys b Kappa', '25:12-16/30259:2-8'),
    [{ text: 'a ' }, { emote: '30259', alt: 'HeyGuys' }, { text: ' b ' }, { emote: '25', alt: 'Kappa' }]);
  // broken or hostile ranges are ignored, never thrown on
  assert.deepEqual(T.emotePieces('hi', '25:0-9'), [{ text: 'hi' }]);
  assert.deepEqual(T.emotePieces('hi', '"><img>:0-1'), [{ text: 'hi' }]);
  assert.deepEqual(T.emotePieces('hi', 'a.b:0-1'), [{ text: 'hi' }]);
  assert.deepEqual(T.emotePieces('hello', '25:0-2,1-3'), [{ emote: '25', alt: 'hel' }, { text: 'lo' }]);
  assert.deepEqual(T.emotePieces('', ''), []);
  assert.deepEqual(T.emotePieces('😀 Kappa', '25:2-6'), [{ text: '😀 ' }, { emote: '25', alt: 'Kappa' }]);
  assert.deepEqual(T.emotePieces('hi Kappa', '25:3-7'), [{ text: 'hi ' }, { emote: '25', alt: 'Kappa' }]);
  assert.deepEqual(T.emotePieces('plain', ''), [{ text: 'plain' }]);
  assert.deepEqual(T.emotePieces('x', '<bad>:0-0'), [{ text: 'x' }]);
});

test('alert wording', () => {
  assert.deepEqual(T.fillParts('{name} cheered {amount}!', { name: 'Ana', amount: '100 bits' }),
    [{ key: 'name', value: 'Ana' }, { text: ' cheered ' }, { key: 'amount', value: '100 bits' }, { text: '!' }]);
  assert.deepEqual(T.fillParts('{name} resubscribed! {amount}', { name: 'Ana', amount: '' }), [{ key: 'name', value: 'Ana' }, { text: ' resubscribed! ' }]);
});

test('viewer colours stay readable', () => {
  const dark = T.merge({});
  const light = T.merge({ colors: { background: '#fffaf2', backgroundOpacity: 0.95 } });
  assert.ok(T.contrast(T.readable('#000080', dark), dark.colors.background) >= 3);
  assert.ok(T.contrast(T.readable('#ffff00', light), light.colors.background) >= 3);
  assert.equal(T.readable('not a colour', dark), null);
  assert.equal(T.lightSurface(light), true);
  assert.equal(T.lightSurface(dark), false);
  assert.equal(T.ink('#ffd400'), '#0b0f14');
  assert.equal(T.ink('#1d2733'), '#ffffff');
  const fixed = T.merge({ colors: { name: 'fixed', nameColor: '#123456' } });
  assert.equal(T.nameColor({ p: 'twitch', color: '#ff0000' }, fixed), '#123456');
  assert.equal(T.nameColor({ p: 'kick', color: '' }, dark), T.readable(dark.colors.kick, dark));
});

test('theme names', () => {
  assert.equal(T.validName('my-theme-2'), true);
  assert.equal(T.validName('-bad'), false);
  assert.equal(T.validName('Bad'), false);
  assert.equal(T.validName('a'.repeat(41)), false);
  assert.equal(T.slug('My Cool Theme (copy)'), 'my-cool-theme-copy');
  assert.equal(T.slug('!!!'), 'my-theme');
});

test('css variables cover every platform and switch', () => {
  const vars = T.cssVars(T.merge({ colors: { outlineWidth: 2 }, message: { platform: 'bar', accentWidth: 1 } }));
  for (const p of T.PLATFORMS) assert.match(vars['--cc-' + p], /^#[0-9a-f]{6}$/);
  assert.equal(vars['--cc-bar'], '3px');                      // a bar is never thinner than 3px
  assert.match(vars['--cc-text-shadow'], /2px 0px 0 #000000/);
  assert.equal(T.cssVars(T.merge({ message: { accentBar: false } }))['--cc-bar'], '0px');
  assert.equal(T.cssVars(T.merge({ font: { google: 'Inter' } }))['--cc-font'].startsWith('"Inter", '), true);
  const s = T.switches(T.merge({ chat: { direction: 'top' } }));
  assert.equal(s.direction, 'top');
  assert.equal(s.surface, 'dark');
});

test('every built-in preset is valid', () => {
  const files = readdirSync(presetDir).filter((f) => f.endsWith('.json'));
  assert.equal(files.length, 8);
  for (const f of files) {
    const raw = JSON.parse(readFileSync(path.join(presetDir, f), 'utf8'));
    assert.deepEqual(T.problems(raw), [], f);
    assert.equal(raw.schema, 1, f);
    const t = T.merge(raw);
    assert.ok(t.label && t.label !== 'Untitled', f + ' has a label');
    assert.ok(T.validName(f.slice(0, -5)), f + ' has a usable file name');
    assert.ok(T.contrast(t.colors.text, t.colors.background) >= 4.5 || t.colors.backgroundOpacity < 0.35, f + ' text contrast');
    assert.ok(Object.keys(T.cssVars(t)).length > 25, f);
  }
});

test('icons exist for every platform', () => {
  for (const p of [...T.PLATFORMS, 'chat']) assert.match(I.PATHS[p], /^M[\d.]/);
  assert.deepEqual(Object.keys(I.NAMES).sort(), [...T.PLATFORMS].sort());
  for (const p of Object.keys(A.NAMES)) assert.ok(I.PATHS[p] && I.NAMES[p], p + ' has an icon and a name');
  for (const p of T.PLATFORMS) assert.match(T.DEFAULTS.colors[p], /^#[0-9a-f]{6}$/i);
});

const PNG = 'data:image/png;base64,iVBORw0KGgo=', WEBP = 'data:image/webp;base64,UklGRg==';

test('a logo for one platform beats the one for every platform, which beats the built-in', () => {
  assert.equal(T.logoFor(T.merge({}), 'twitch'), '');
  const every = T.merge({ logos: { all: PNG } });
  assert.equal(T.logoFor(every, 'twitch'), PNG);
  assert.equal(T.logoFor(every, 'rumble'), PNG);
  const both = T.merge({ logos: { all: PNG, twitch: WEBP } });
  assert.equal(T.logoFor(both, 'twitch'), WEBP);
  assert.equal(T.logoFor(both, 'youtube'), PNG);
  assert.equal(T.logoFor(T.merge({ logos: { all: PNG, kick: 'chat' } }), 'kick'), 'chat');
  assert.equal(T.logoFor(every, 'system'), '', 'only real platforms take a logo');
});

test('a theme file can only hold small pictures as logos', () => {
  const bad = ['data:image/svg+xml;base64,PHN2Zz4=', 'https://example.com/logo.png', 'javascript:alert(1)', 'data:text/html;base64,PGI+',
    'data:image/png;base64,<script>', PNG + ' ', 'data:image/png;base64,' + 'A'.repeat(T.LOGO_MOST), 42, true, ['chat']];
  bad.forEach((value) => {
    assert.equal(T.merge({ logos: { twitch: value } }).logos.twitch, '', String(value).slice(0, 40));
    assert.match(T.problems({ logos: { twitch: value } })[0], /logos\.twitch: not a small PNG, WebP or JPEG/);
  });
  const longest = 'data:image/png;base64,' + 'A'.repeat(T.LOGO_MOST - 'data:image/png;base64,'.length);
  assert.equal(T.merge({ logos: { twitch: longest } }).logos.twitch, longest, 'exactly at the limit is fine');
  assert.deepEqual(T.problems({ logos: { nope: PNG } }), ['logos.nope: unknown key, ignored']);
});

test('platform names: renamed, the same for every platform, or hidden', () => {
  const built = 'Twitch';
  assert.equal(T.platformName(T.merge({}), 'twitch', built), 'Twitch');
  assert.equal(T.platformName(T.merge({ names: { twitch: 'Main' } }), 'twitch', built), 'Main');
  assert.equal(T.platformName(T.merge({ names: { all: 'Live' } }), 'twitch', built), 'Live');
  assert.equal(T.platformName(T.merge({ names: { all: 'Live', twitch: 'Main' } }), 'twitch', built), 'Main');
  assert.equal(T.platformName(T.merge({ names: { all: '-' } }), 'twitch', built), '');
  assert.equal(T.platformName(T.merge({ names: { all: '-', twitch: 'Main' } }), 'twitch', built), 'Main');
  assert.equal(T.platformName(T.merge({ names: { twitch: '-' } }), 'twitch', built), '');
  assert.equal(T.platformName(T.merge({ names: { twitch: '   ' } }), 'twitch', built), 'Twitch', 'spaces are no name');
  assert.equal(T.platformName(T.merge({ names: { all: 'Live' } }), 'system', 'CrossChat'), 'CrossChat');
  assert.equal(T.merge({ names: { twitch: 'x'.repeat(40) } }).names.twitch.length, 24);
});

test('the short tag follows the name', () => {
  assert.equal(T.platformTag(T.merge({}), 'twitch', 'TW'), 'TW');
  assert.equal(T.platformTag(T.merge({ names: { twitch: 'main' } }), 'twitch', 'TW'), 'MAI');
  assert.equal(T.platformTag(T.merge({ names: { all: '-' } }), 'twitch', 'TW'), '•');
});

test('a hidden name leaves no gap in an alert', () => {
  const t = T.merge({ names: { all: '-' }, alerts: { labels: { sub: '{name} subscribed {platform}' } } });
  assert.equal(T.alertLine({ alert: 'sub', p: 'twitch', name: 'Ann' }, t, T.platformName(t, 'twitch', 'Twitch')), 'Ann subscribed');
});

test('the biggest rendering that fits is the one kept', () => {
  const tried = [];
  const render = (box, type) => { tried.push(box + ' ' + type); return 'data:' + type + ';base64,' + 'A'.repeat(box === 64 ? 100 : T.LOGO_MOST + 1); };
  assert.match(T.shrinkLogo(render), /^data:image\/png;base64,A{100}$/);
  assert.deepEqual(tried, ['128 image/png', '128 image/webp', '96 image/png', '96 image/webp', '64 image/png']);
  assert.equal(T.shrinkLogo(() => 'data:image/png;base64,' + 'A'.repeat(T.LOGO_MOST + 1)), '', 'nothing fits');
  assert.equal(T.shrinkLogo(() => 'data:text/plain;base64,AAAA'), '', 'not a picture');
});

test('a picture goes whole and centred in its square', () => {
  assert.deepEqual(T.logoBox(100, 100, 128), { x: 0, y: 0, w: 128, h: 128 });
  assert.deepEqual(T.logoBox(200, 100, 128), { x: 0, y: 32, w: 128, h: 64 });
  assert.deepEqual(T.logoBox(100, 200, 128), { x: 32, y: 0, w: 64, h: 128 });
  assert.deepEqual(T.logoBox(1000, 1, 48), { x: 0, y: 23, w: 48, h: 1 });
});

test('a theme with every logo at its largest and the longest CSS still fits a theme file', () => {
  const logos = Object.fromEntries(T.LOGO_KEYS.map((k) => [k, 'data:image/png;base64,' + 'A'.repeat(T.LOGO_MOST - 22)]));
  assert.equal(T.LOGO_KEYS.length, 9);
  const full = T.merge({ logos, css: 'x'.repeat(20000) });
  assert.ok(T.LOGO_KEYS.every((k) => full.logos[k].length === T.LOGO_MOST));
  assert.ok(new TextEncoder().encode(JSON.stringify(full, null, 2)).length <= T.THEME_MOST);
});

function fakeDoc() {
  const node = (tag) => ({ tag, attrs: {}, kids: [], setAttribute(k, v) { this.attrs[k] = v; }, appendChild(c) { this.kids.push(c); } });
  return { createElement: node, createElementNS: (ns, tag) => node(tag) };
}

test('a custom logo is an image, never markup; the bubble and the brand are drawn', () => {
  const picture = I.icon('twitch', fakeDoc(), PNG);
  assert.equal(picture.tag, 'img');
  assert.equal(picture.src, PNG);
  assert.equal(picture.alt, '');
  assert.equal(picture.kids.length, 0);
  const bubble = I.icon('twitch', fakeDoc(), 'chat');
  assert.equal(bubble.tag, 'svg');
  assert.equal(bubble.kids[0].attrs.d, I.PATHS.chat);
  assert.equal(I.icon('twitch', fakeDoc(), '').kids[0].attrs.d, I.PATHS.twitch);
  assert.equal(I.icon('twitch', fakeDoc()).kids[0].attrs.d, I.PATHS.twitch);
});
