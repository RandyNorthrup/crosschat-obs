// A stand-in for a browser tab, so the tests can run the real page scripts in Node: a small DOM built from the page's own
// HTML, an address, a clock the test moves by hand, and fetch, EventSource and postMessage that do what the test says.
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const read = (path) => readFileSync(new URL('../../' + path, import.meta.url), 'utf8');
const VOID = new Set(['meta', 'link', 'input', 'img', 'br', 'hr', 'source', 'circle', 'path']);
const camel = (name) => name.replace(/-([a-z])/g, (all, c) => c.toUpperCase());

class Text {
  constructor(text) { this.nodeType = 3; this.textContent = String(text); this.parentNode = null; }
  remove() { if (this.parentNode) this.parentNode.childNodes.splice(this.parentNode.childNodes.indexOf(this), 1); this.parentNode = null; }
}

// One compound selector ("button.chip:not(.edit)[data-x]") against one element.
function matchesOne(el, part) {
  const nots = [];
  const own = part.replace(/:not\(([^)]*)\)/g, (all, inside) => { nots.push(inside); return ''; });
  if (nots.some((inside) => matchesOne(el, inside))) return false;
  const tag = /^[a-zA-Z][\w-]*/.exec(own);
  if (tag && el.localName !== tag[0].toLowerCase()) return false;
  for (const [, kind, name] of own.replace(/\[[^\]]*\]/g, '').matchAll(/([#.])([\w-]+)/g)) {
    if (kind === '#' ? el.id !== name : !el.classes.has(name)) return false;
  }
  for (const [, name, wanted] of own.matchAll(/\[([\w-]+)(?:="?([^"\]]*)"?)?\]/g)) {
    const got = el.getAttribute(name);
    if (got == null || (wanted !== undefined && got !== wanted)) return false;
  }
  return true;
}
function matches(el, selector) {
  return selector.split(',').some((one) => {
    const parts = one.trim().split(/\s+/);
    if (!matchesOne(el, parts[parts.length - 1])) return false;
    let up = el.parentNode;
    for (let i = parts.length - 2; i >= 0; i--) {
      while (up && !(up instanceof Element && matchesOne(up, parts[i]))) up = up.parentNode;
      if (!up) return false;
      up = up.parentNode;
    }
    return true;
  });
}

class Element {
  constructor(tag, doc) {
    this.nodeType = 1; this.localName = tag.toLowerCase(); this.tagName = tag.toUpperCase(); this.ownerDocument = doc;
    this.childNodes = []; this.parentNode = null; this.dataset = {}; this.attrs = new Map(); this.listeners = new Map(); this.hidden = false;
    this.classes = new Set(); this.id = ''; this.value = ''; this.scrollTop = 0; this.scrollHeight = 0; this.clientHeight = 0; this.open = false;
    const vars = new Map();
    this.style = { setProperty: (k, v) => vars.set(k, String(v)), getPropertyValue: (k) => vars.get(k) || '', removeProperty: (k) => vars.delete(k) };
    this.classList = {
      add: (...n) => n.forEach((c) => this.classes.add(c)), remove: (...n) => n.forEach((c) => this.classes.delete(c)), contains: (c) => this.classes.has(c),
      toggle: (c, on) => { const want = on === undefined ? !this.classes.has(c) : !!on; if (want) this.classes.add(c); else this.classes.delete(c); return want; },
    };
  }
  get className() { return [...this.classes].join(' '); }
  set className(v) { this.classes = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get children() { return this.childNodes.filter((n) => n instanceof Element); }
  get options() { return this.children.filter((n) => n.localName === 'option'); }
  get firstChild() { return this.childNodes[0] || null; }
  get lastChild() { return this.childNodes[this.childNodes.length - 1] || null; }
  get firstElementChild() { return this.children[0] || null; }
  get isConnected() { let n = this; while (n.parentNode) n = n.parentNode; return n === this.ownerDocument.documentElement; }
  get textContent() { return this.childNodes.map((n) => n.textContent).join(''); }
  set textContent(v) { this.detachAll(); if (v != null && v !== '') this.push(new Text(v)); }
  detachAll() { this.childNodes.forEach((n) => { n.parentNode = null; }); this.childNodes = []; }
  push(node, at = this.childNodes.length) {
    if (node.parentNode) node.remove();
    node.parentNode = this; this.childNodes.splice(at, 0, node);
  }
  node(v) { return v instanceof Element || v instanceof Text ? v : new Text(v); }
  append(...nodes) { nodes.forEach((n) => this.push(this.node(n))); }
  appendChild(n) { this.push(n); return n; }
  prepend(...nodes) { nodes.reverse().forEach((n) => this.push(this.node(n), 0)); }
  insertBefore(n, before) { this.push(n, before ? this.childNodes.indexOf(before) : this.childNodes.length); return n; }
  remove() { if (this.parentNode) this.parentNode.childNodes.splice(this.parentNode.childNodes.indexOf(this), 1); this.parentNode = null; }
  replaceChildren(...nodes) { this.detachAll(); this.append(...nodes); }
  replaceWith(n) { const up = this.parentNode, at = up.childNodes.indexOf(this); this.remove(); up.push(n, at); }
  setAttribute(k, v) {
    if (k === 'class') this.className = v;
    else if (k === 'id') this.id = v;
    else if (k.startsWith('data-')) this.dataset[camel(k.slice(5))] = String(v);
    else this.attrs.set(k, String(v));
  }
  getAttribute(k) {
    if (k === 'class') return this.className;
    if (k === 'id') return this.id || null;
    if (k.startsWith('data-')) return this.dataset[camel(k.slice(5))] ?? null;
    return this.attrs.has(k) ? this.attrs.get(k) : null;
  }
  hasAttribute(k) { return this.getAttribute(k) != null; }
  removeAttribute(k) { this.attrs.delete(k); }
  all() { return this.children.flatMap((c) => [c, ...c.all()]); }
  querySelectorAll(s) { return this.all().filter((e) => matches(e, s)); }
  querySelector(s) { return this.querySelectorAll(s)[0] || null; }
  closest(s) { let n = this; while (n && n instanceof Element) { if (matches(n, s)) return n; n = n.parentNode; } return null; }
  contains(o) { for (let n = o; n; n = n.parentNode) if (n === this) return true; return false; }
  addEventListener(type, fn) { (this.listeners.get(type) || this.listeners.set(type, new Set()).get(type)).add(fn); }
  removeEventListener(type, fn) { const set = this.listeners.get(type); if (set) set.delete(fn); }
  dispatch(type, init) {
    const e = { type, target: this, preventDefault() {}, stopPropagation() {}, ...init };
    if (this['on' + type]) this['on' + type](e);
    [...(this.listeners.get(type) || [])].forEach((fn) => fn(e));
  }
  listening(type) { return (this.listeners.get(type) || new Set()).size; }
  click() { this.dispatch('click'); }
  focus() { this.ownerDocument.activeElement = this; }
  blur() {}
  scrollIntoView() {}
  setSelectionRange() {}
  showModal() { this.open = true; }
  close() { this.open = false; }
  getBoundingClientRect() { return { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 }; }
}

function makeDocument(html) {
  const doc = {
    activeElement: null, visibilityState: 'visible', listeners: new Map(),
    createElement: (tag) => new Element(tag, doc), createElementNS: (ns, tag) => new Element(tag, doc), createTextNode: (t) => new Text(t),
    getElementById: (id) => doc.documentElement.all().concat(doc.documentElement).find((e) => e.id === id) || null,
    querySelector: (s) => doc.documentElement.querySelector(s), querySelectorAll: (s) => doc.documentElement.querySelectorAll(s),
    addEventListener() {}, removeEventListener() {},
  };
  doc.documentElement = new Element('html', doc);
  const stack = [doc.documentElement];
  const tags = /<!--[\s\S]*?-->|<!doctype[^>]*>|<(script|style)\b[^>]*>[\s\S]*?<\/\1>|<\/([\w-]+)\s*>|<([\w-]+)((?:\s+[\w:-]+(?:=(?:"[^"]*"|'[^']*'|[^\s>"'][^\s>]*))?)*)\s*(\/?)>|([^<]+)/gi;
  for (const [, raw, close, open, attrs, self, text] of html.matchAll(tags)) {
    if (raw) continue;
    const top = stack[stack.length - 1];
    if (close) { if (stack.length > 1 && stack[stack.length - 1].localName === close.toLowerCase()) stack.pop(); continue; }
    if (text !== undefined) { if (text.trim()) top.push(new Text(text)); continue; }
    if (!open || open.toLowerCase() === 'html') continue;
    const el = new Element(open, doc);
    for (const [, k, dq, sq, plain] of (attrs || '').matchAll(/([\w:-]+)(?:=(?:"([^"]*)"|'([^']*)'|([^\s>]*)))?/g)) {
      if (k === 'hidden') el.hidden = true; else el.setAttribute(k, dq ?? sq ?? plain ?? '');
    }
    if (el.attrs.has('value')) el.value = el.attrs.get('value');
    top.push(el);
    if (!VOID.has(open.toLowerCase()) && !self) stack.push(el);
  }
  doc.head = doc.documentElement.querySelector('head') || new Element('head', doc);
  doc.body = doc.documentElement.querySelector('body') || new Element('body', doc);
  return doc;
}

// A clock moved by hand: setTimeout and setInterval only fire from advance().
function makeClock() {
  let now = 1800000000000, seq = 0;
  const timers = new Map();
  const add = (fn, ms, every) => { const id = ++seq; timers.set(id, { fn, at: now + Math.max(0, Number(ms) || 0), every }); return id; };
  const settle = () => new Promise((r) => setImmediate(r));
  return {
    now: () => now, settle, add, drop: (id) => timers.delete(id),
    async advance(ms) {
      const until = now + ms;
      for (;;) {
        const next = [...timers.entries()].filter(([, t]) => t.at <= until).sort((a, b) => a[1].at - b[1].at)[0];
        if (!next) break;
        const [id, t] = next;
        now = t.at;
        if (t.every != null) t.at = now + Math.max(1, t.every); else timers.delete(id);
        t.fn();
        await settle();
      }
      now = until;
      await settle();
    },
  };
}

// A page at `url` running `scripts` (paths from the repository root) over the HTML in `html`. fetch: { path: answer },
// where an answer is { status, json, text } or a function of (path, init) giving one (or a promise of one); a missing path is a 404.
export async function openPage(html, scripts, { url, routes = {}, platform = 'Win32', dataset = {} } = {}) {
  const clock = makeClock();
  const doc = makeDocument(read(html));
  Object.assign(doc.documentElement.dataset, dataset);
  const address = new URL(url);
  const page = { document: doc, clock, feeds: [], fetched: [], posted: [], routes, listeners: new Map(), animation: { animationName: 'none', animationDuration: '0s', animationDelay: '0s' } };
  class EventSource { constructor(where) { this.url = where; this.closed = false; page.feeds.push(this); } close() { this.closed = true; } }
  async function fetchFake(path, init = {}) {
    page.fetched.push({ path, init });
    const route = routes[String(path).split('?')[0]];
    const a = await (typeof route === 'function' ? route(path, init) : route);
    if (a === undefined) return { ok: false, status: 404, json: async () => ({}), text: async () => '' };
    if (a instanceof Error) throw a;
    const status = a.status || 200;
    return { ok: status < 400, status, json: async () => { if (a.notJson) throw new SyntaxError('not JSON'); return a.json; }, text: async () => a.text || '' };
  }
  const sandbox = {
    document: doc, location: address, navigator: { platform, language: 'en-US' }, fetch: fetchFake, EventSource, console,
    URL, URLSearchParams, TextEncoder, TextDecoder,
    setTimeout: (fn, ms) => clock.add(fn, ms), clearTimeout: (id) => clock.drop(id),
    setInterval: (fn, ms) => clock.add(fn, ms, ms), clearInterval: (id) => clock.drop(id),
    requestAnimationFrame: (fn) => clock.add(() => fn(clock.now()), 16), cancelAnimationFrame: (id) => clock.drop(id),
    performance: { now: () => clock.now() }, __clock: clock,
    localStorage: (() => { const m = new Map(); return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) }; })(),
    sessionStorage: (() => { const m = new Map(); return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) }; })(),
    history: { replaceState() {} },
    matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
    getComputedStyle: () => ({ getPropertyValue: () => '', ...page.animation }),
    CSS: { escape: (s) => String(s) },
    Option: class extends Element { constructor(text, value) { super('option', doc); this.textContent = text; this.value = value; } },
    Image: class extends Element { constructor() { super('img', doc); } },
    addEventListener: (type, fn) => { (page.listeners.get(type) || page.listeners.set(type, new Set()).get(type)).add(fn); },
    removeEventListener: (type, fn) => { const s = page.listeners.get(type); if (s) s.delete(fn); },
    postMessage: (data, origin) => page.posted.push({ data, origin }),
    open() { return null; }, close() {}, parent: null, isSecureContext: false,
  };
  sandbox.window = sandbox.self = sandbox.parent = sandbox;
  page.window = sandbox;
  const context = vm.createContext(sandbox);
  vm.runInContext('Date.now = () => __clock.now();', context);
  page.script = (path) => vm.runInContext(read(path), context, { filename: path });
  page.$ = (id) => doc.getElementById(id);
  page.feed = () => page.feeds[page.feeds.length - 1];
  page.said = (m) => page.feed().onmessage({ data: JSON.stringify(m) });
  page.message = (data) => [...(page.listeners.get('message') || [])].forEach((fn) => fn({ source: vm.runInContext('window', context), origin: address.origin, data }));
  page.run = (code) => vm.runInContext(code, context);
  page.settle = clock.settle;
  page.advance = clock.advance;
  scripts.forEach(page.script);
  await clock.settle();
  return page;
}
