// The on-stream widgets and the chat window as whole pages (tests/js/fake-page.mjs stands in for the browser).
// Run: node --test "tests/js/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { openPage } from './fake-page.mjs';

const CHAT = 'http://127.0.0.1:4466/';
const ok = (json) => ({ json });

// ---- the on-stream widgets ----------------------------------------------------------------------------------------
const WIDGET_SCRIPTS = ['hub/web/theme.js', 'hub/web/icons.js', 'hub/web/feed.js', 'hub/web/widgets.js'];

async function widget(address, { overlay = {}, theme = {}, name = 'classic' } = {}) {
  const routes = { '/settings': ok({ overlay, theme: name }), ['/themes/' + name]: ok(theme), '/themes/mine': ok(theme) };
  const page = await openPage('hub/web/overlay.html', WIDGET_SCRIPTS, { url: CHAT.slice(0, -1) + address, routes });
  await page.settle();
  return page;
}

const message = (page, id, p, extra) => ({ type: 'msg', kind: 'chat', id, p, name: p + '_viewer', text: 'hello', t: page.clock.now(), ...extra });

function onScreen(page) {                     // the platforms of the chat lines showing, in order
  return page.document.querySelectorAll('.cc-msg').map((el) => el.dataset.platform);
}

async function chatFrom(page, platforms) {
  page.said({ type: 'status', live: true, status: {} });
  platforms.forEach((p, i) => page.said(message(page, 'm' + i, p)));
  await page.settle();
  return onScreen(page);
}

const EVERY = ['twitch', 'youtube', 'kick'];

test('overlay.platforms in config.json decides what the on-stream chat shows (the setting the README gives for Twitch)', async () => {
  const page = await widget('/overlay/chat', { overlay: { platforms: ['twitch'] } });
  assert.deepEqual([...await chatFrom(page, EVERY)], ['twitch']);
});

test('the default theme comes from /settings; /themes is not needed', async () => {
  const page = await widget('/overlay/chat', { name: 'mine', overlay: { platforms: 'all' } });
  assert.deepEqual(page.fetched.map((f) => f.path), ['/settings', '/themes/mine']);
});

test("a theme's own list beats overlay.platforms, and ?platforms= beats both", async () => {
  let page = await widget('/overlay/chat', { overlay: { platforms: ['twitch'] }, theme: { chat: { platforms: ['kick'] } } });
  assert.deepEqual([...await chatFrom(page, EVERY)], ['kick']);
  page = await widget('/overlay/chat?platforms=youtube', { overlay: { platforms: ['twitch'] }, theme: { chat: { platforms: ['kick'] } } });
  assert.deepEqual([...await chatFrom(page, EVERY)], ['youtube']);
});

test('a theme named in the address still gets overlay.platforms', async () => {
  const page = await widget('/overlay/chat?theme=mine', { overlay: { platforms: ['twitch'] } });
  assert.ok(page.fetched.some((f) => f.path === '/themes/mine'));
  assert.deepEqual([...await chatFrom(page, EVERY)], ['twitch']);
});

test('overlay.platforms holds through a moment the hub cannot be read', async () => {
  const page = await widget('/overlay/chat', { overlay: { platforms: ['twitch'] } });
  page.routes['/settings'] = new Error('Failed to fetch');
  page.said({ type: 'theme', name: 'classic' });              // asks the hub again
  await page.settle();
  assert.deepEqual([...await chatFrom(page, EVERY)], ['twitch']);
});

test('only the address picks the widget', async () => {
  const page = await widget('/overlay/alerts?widget=chat');
  assert.equal(page.document.documentElement.dataset.widget, 'alerts');
  const none = await widget('/overlay/?widget=alerts');        // (not an address the hub serves)
  assert.equal(none.document.documentElement.dataset.widget, 'chat');
});

// An alert on screen, past its time, and on its way out.
async function leavingAlert(animation) {
  const page = await widget('/overlay/alerts', { theme: { alerts: { seconds: 1 } } });
  page.animation = animation;
  page.said({ type: 'status', live: true, status: {} });
  page.said({ type: 'msg', kind: 'event', alert: 'sub', id: 'a1', p: 'twitch', name: 'ann', text: '', t: page.clock.now() });
  await page.settle();
  const el = page.document.querySelector('.cc-alert');
  assert.ok(el, 'the alert is showing');
  await page.advance(1000);
  assert.ok(el.classList.contains('cc-out'), 'it is leaving');
  return { page, el };
}
const FADE = { animationName: 'cc-alert-out', animationDuration: '0.45s', animationDelay: '0s' };

test('a widget leaves when its own animation ends, not at a guess', async () => {
  const { page, el } = await leavingAlert(FADE);
  assert.ok(el.isConnected, 'still there while it animates');
  el.dispatch('animationend');
  assert.equal(el.isConnected, false);
  assert.equal(el.listening('animationend'), 0);
});

test('an animation the browser calls off counts as ended', async () => {
  const { el } = await leavingAlert(FADE);
  el.dispatch('animationcancel');
  assert.equal(el.isConnected, false);
});

test("the end of something else's animation doesn't count", async () => {
  const { el } = await leavingAlert(FADE);
  el.dispatch('animationend', { pseudoElement: '::before' });  // the alert's shine
  el.dispatch('animationend', { target: el.firstChild });      // something inside it
  assert.ok(el.isConnected);
});

test('with animations switched off (a theme\'s custom CSS), a widget still leaves, at once', async () => {
  const { el } = await leavingAlert({ animationName: 'none', animationDuration: '0s', animationDelay: '0s' });
  assert.equal(el.isConnected, false);
  const { el: none } = await leavingAlert({ animationName: 'cc-alert-out', animationDuration: '0s', animationDelay: '0s' });
  assert.equal(none.isConnected, false);
});

test('when the animation never runs (a source OBS has hidden), the clock takes it off instead', async () => {
  const { page, el } = await leavingAlert(FADE);
  await page.advance(449);
  assert.ok(el.isConnected, 'not before the animation could have ended');
  await page.advance(251);
  assert.equal(el.isConnected, false);
});

test('the next alert waits until the one before has really gone', async () => {
  const page = await widget('/overlay/alerts', { theme: { alerts: { seconds: 1 } } });
  page.animation = FADE;
  page.said({ type: 'status', live: true, status: {} });
  ['a1', 'a2'].forEach((id) => page.said({ type: 'msg', kind: 'event', alert: 'sub', id, p: 'twitch', name: id, text: '', t: page.clock.now() }));
  await page.settle();
  const first = page.document.querySelector('.cc-alert');
  await page.advance(1000);
  assert.equal(page.document.querySelectorAll('.cc-alert').length, 1);
  first.dispatch('animationend');
  await page.advance(350);
  assert.deepEqual(page.document.querySelectorAll('.cc-alert').map((a) => a.dataset.id), ['a2']);
});

// ---- the chat window -------------------------------------------------------------------------------------------------
const CHAT_SCRIPTS = ['hub/web/vendor/qrcode.js', 'hub/web/feed.js', 'hub/web/theme.js', 'hub/web/app.js'];
const THIS_PC = { remote: false, device: null, version: '1.9.0', lan_url: null, app: 'obs' };
const WITH_EXTENSION = { crosschat: '1.8.0', crosschatWindows: '1' };   // what bridge.js puts on the page

async function chatWindow({ whoami = ok(THIS_PC), platform = 'Win32', address = CHAT, dataset = {}, routes = {} } = {}) {
  const page = await openPage('hub/web/window.html', CHAT_SCRIPTS, {
    url: address, platform, dataset,
    routes: { '/whoami': whoami, '/config/editable': ok({ settings: {}, restart: [], custom_window: false, first_run: false }), '/outbox/result': ok({ ok: true }), ...routes },
  });
  await page.settle();
  return page;
}

test('a bug while drawing a message is not swallowed; only a line that is not JSON is', async () => {
  const page = await chatWindow();
  assert.doesNotThrow(() => page.feed().onmessage({ data: 'not json' }));
  page.$('total').replaceChildren();                           // the next viewer count finds nothing to write in: a bug
  assert.throws(() => page.said({ type: 'viewers', counts: {}, total: 3 }), (e) => e.name === 'TypeError');
});

test('Settings on a Mac has no Tailscale switch (the hub has no Tailscale there)', async () => {
  const mac = await chatWindow({ platform: 'MacIntel' });
  mac.$('gear').click();
  assert.equal(mac.$('tailscale-row').hidden, true);
  assert.equal(mac.$('tailscale-hint').hidden, true);
  const windows = await chatWindow({ platform: 'Win32' });
  windows.$('gear').click();
  assert.equal(windows.$('tailscale-row').hidden, false);
  assert.equal(windows.$('tailscale-hint').hidden, false);
});

test('the message box stops no reply the hub would take, and an emoji counts as two in it', async () => {
  const page = await chatWindow();
  assert.ok(page.$('say').maxLength >= 2 * 8000);              // Facebook takes 8000 characters, each of them perhaps an emoji
});

test('?demo is gone from the chat window: it talks to the hub like any other', async () => {
  const page = await chatWindow({ address: CHAT + '?demo=mod' });
  assert.deepEqual(page.fetched[0].path, '/whoami');
  assert.equal(page.feeds.length, 1);
  assert.equal(page.document.querySelectorAll('#list .m').length, 0);
});

test('when /whoami fails the window waits for an answer: it never guesses it is the one on this PC', async () => {
  const page = await chatWindow({ whoami: new Error('Failed to fetch') });
  assert.equal(page.feeds.length, 0, 'not connected as the window on this PC');
  assert.equal(page.$('lost').style.display, 'inline');
  page.routes['/whoami'] = { notJson: true };                  // something answered, not the hub
  await page.advance(2000);
  assert.equal(page.feeds.length, 0);
  page.routes['/whoami'] = { status: 500, json: { error: 'not now' } };
  await page.advance(2000);
  assert.equal(page.feeds.length, 0);
  page.routes['/whoami'] = ok({ remote: true, device: 'Phone', version: '1.9.0', lan_url: null, app: 'obs' });
  await page.advance(2000);
  assert.equal(page.feeds.length, 1);
  assert.equal(page.feed().url, '/events');                    // a paired device: not the executor, not the speaker
  assert.equal(page.$('device').hidden, false);
});

test('a device no longer paired is told so at once', async () => {
  const page = await chatWindow({ whoami: { status: 401 } });
  assert.equal(page.feeds.length, 0);
  assert.match(page.$('notice').querySelector('span').textContent, /no longer paired/);
});

const EXTENSION_PLATFORMS = ['YouTube', 'X', 'TikTok', 'Facebook', 'Instagram', 'Rumble'];

test('the notice names every chat a reply needs the extension for', async () => {
  const remote = await chatWindow({ whoami: ok({ remote: true, device: 'Phone', version: '1.9.0', lan_url: null, app: 'obs' }) });
  remote.said({ type: 'executor', present: false });
  const onPhone = remote.$('notice').querySelector('span').textContent;
  assert.match(onPhone, /^Replies to YouTube, X, TikTok, Facebook, Instagram and Rumble need the CrossChat window open on the streaming PC/);
  const here = await chatWindow();
  here.said({ type: 'executor', present: false });
  const onPC = here.$('notice').querySelector('span').textContent;
  assert.match(onPC, /^Replies to YouTube, X, TikTok, Facebook, Instagram and Rumble go out through the CrossChat window/);
  EXTENSION_PLATFORMS.forEach((p) => { assert.ok(onPhone.includes(p), p); assert.ok(onPC.includes(p), p); });
});

// The hub asks the chat window to close itself, and the extension answers.
async function askedToClose(routes) {
  const page = await chatWindow({ dataset: WITH_EXTENSION, routes });
  page.said({ type: 'outbox', job: { id: 'job1', kind: 'window', action: 'close', role: 'chat', url: '', box: null, window: 0, known: [], wait: 0 } });
  assert.equal(page.posted[0].data.action, 'close');
  page.message({ crosschat: 'windowed', n: page.posted[0].data.n, answer: { ok: true, windows: [5] } });
  await page.settle();
  return page;
}
const answered = (page) => page.posted.filter((p) => p.data.crosschat === 'window' && p.data.action === 'answered');

test('the chat window asks to be closed only after its answer has reached the hub', async () => {
  let land;
  const page = await askedToClose({ '/outbox/result': () => new Promise((r) => { land = () => r(ok({ ok: true })); }) });
  const posted = page.fetched.filter((f) => f.path === '/outbox/result');
  assert.equal(posted.length, 1);
  assert.deepEqual(JSON.parse(posted[0].init.body), { job_id: 'job1', answer: { ok: true, windows: [5] } });
  assert.equal(answered(page).length, 0, 'the answer is still on its way');
  land();
  await page.settle();
  assert.equal(answered(page).length, 1);
  assert.equal(answered(page)[0].data.role, 'chat');
  assert.equal(answered(page)[0].origin, new URL(CHAT).origin);
});

test('with the hub gone, the chat window still says so: it has nothing left to wait for', async () => {
  const page = await askedToClose({ '/outbox/result': new Error('Failed to fetch') });
  assert.equal(answered(page).length, 1);
});

test('only closing the chat window itself is announced', async () => {
  const page = await chatWindow({ dataset: WITH_EXTENSION });
  page.said({ type: 'outbox', job: { id: 'j2', kind: 'window', action: 'close', role: 'x', url: 'https://studio.x.com/live', box: null, window: 0, known: [], wait: 0 } });
  page.message({ crosschat: 'windowed', n: page.posted[0].data.n, answer: { ok: true } });
  page.said({ type: 'outbox', job: { id: 'j3', kind: 'send', to: ['x'], text: 'hi' } });
  page.message({ crosschat: 'sent', n: page.posted[1].data.n, answer: { x: { ok: true } } });
  await page.settle();
  assert.equal(answered(page).length, 0);
});
