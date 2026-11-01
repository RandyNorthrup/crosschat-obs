// Tests for extension/youtube.js: which button opens a chat message's own menu.
// Run: node --test "tests/js/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const YT = require('../../extension/youtube.js');

// A chat row's buttons in page order, each with the selectors it matches. querySelector behaves like the browser's:
// with a selector list, the first button in the row that matches any of them.
function row(buttons) {
  const matches = (b, list) => list.split(',').map((s) => s.trim()).some((s) => b.selectors.includes(s));
  return {
    querySelector: (list) => buttons.find((b) => matches(b, list)) || null,
    querySelectorAll: (list) => buttons.filter((b) => matches(b, list)),
  };
}

// As YouTube's live chat showed a top fan's message on 31 October 2026: the "#1" rank button comes first,
// the "Chat actions" menu (div#menu > yt-icon-button#menu-button > button#button) last.
const rank = { name: 'rank', selectors: ['button[aria-label]'] };
const menu = { name: 'menu', selectors: ['#menu-button button', '#menu button', 'button[aria-label]', 'button[aria-label="Chat actions"]'] };

test('the menu button is found even when a top-fan rank button comes first', () => {
  const item = row([rank, menu]);
  assert.equal(item.querySelector('#menu-button button, #menu button, button[aria-label]').name, 'rank');  // the old way
  assert.equal(YT.menuButton(item).name, 'menu');
});

test('the menu is found by its label when YouTube drops the ids', () => {
  const labelled = { name: 'menu', selectors: ['button[aria-label]', 'button[aria-label="Chat actions"]'] };
  assert.equal(YT.menuButton(row([rank, labelled])).name, 'menu');
});

test('a row without a menu (not the owner or a moderator) clicks nothing', () => {
  assert.equal(YT.menuButton(row([rank])), null);
  assert.equal(YT.menuButton(row([])), null);
});

test('the embedded chat (the copy inside the CrossChat window) is told apart from the chat pop-out', () => {
  assert.equal(YT.embedded('?v=Ilc1JaZfDxA&embed_domain=127.0.0.1'), true);
  assert.equal(YT.embedded('?is_popout=1&v=Ilc1JaZfDxA'), false);
  assert.equal(YT.embedded('?v=Ilc1JaZfDxA'), false);
});

test('a timeout asks YouTube for the length nearest the one asked for, 5 minutes by default', () => {
  const pick = (s) => YT.timeoutChoice(s)[0];
  assert.equal(pick(0), 300);
  assert.equal(pick(undefined), 300);
  assert.equal(pick(300), 300);
  assert.equal(pick(600), 600);
  assert.equal(pick(3600), 1800);
  assert.equal(pick(1209600), 86400);
  assert.equal(pick(5), 10);
});

// YouTube's "Timeout duration" dialog as it showed on 31 October 2026: six radios (5 minutes checked), Confirm, Cancel.
function dialog(labels = ['10 seconds', '1 minute', '5 minutes', '10 minutes', '30 minutes', '24 hours'], buttons = ['Confirm', 'Cancel']) {
  const radios = labels.map((l) => ({ label: l, getAttribute: (a) => (a === 'aria-label' ? l : null) }));
  const btns = buttons.map((b) => ({ innerText: b, getAttribute: () => null }));
  return { radios, btns, querySelectorAll: (s) => (s === '[role="radio"]' ? radios : s === 'button' ? btns : []) };
}

test("the timeout dialog's radio and Confirm button are found", () => {
  const d = dialog();
  const got = YT.timeoutDialog([d], 300);
  assert.equal(got.dialog, d);
  assert.equal(got.radio.label, '5 minutes');
  assert.equal(got.yes.innerText, 'Confirm');
  assert.equal(YT.timeoutDialog([d], 86400).radio.label, '24 hours');
});

test('a dialog without radios or without Confirm is not the timeout dialog', () => {
  assert.equal(YT.timeoutDialog([dialog([])], 300), null);
  assert.equal(YT.timeoutDialog([dialog(undefined, ['Cancel'])], 300), null);
  assert.equal(YT.timeoutDialog([], 300), null);
});

test("a menu entry or dialog counts as open by YouTube's own aria-hidden, not by being drawn", () => {
  // a background tab draws nothing until someone looks; YouTube marks a closed menu or dialog aria-hidden="true"
  const inside = (hiddenAncestor) => ({ closest: (s) => (s === '[aria-hidden="true"]' && hiddenAncestor ? {} : null) });
  assert.equal(YT.shown(inside(false)), true);
  assert.equal(YT.shown(inside(true)), false);
  assert.equal(YT.shown(null), false);
});

test('waiting goes by the clock and returns what was found', async () => {
  let n = 0;
  assert.equal(await YT.waitFor(() => (++n >= 2 ? 'menu' : null), 2000), 'menu');
  const started = Date.now();
  assert.equal(await YT.waitFor(() => null, 300), null);
  assert.ok(Date.now() - started >= 300);
});

test('the menu entries CrossChat picks are the ones YouTube shows the channel owner', () => {
  // the owner's menu on that live: Channel Activity, Go to channel, Pin message, Report, Remove, Put user in timeout,
  // Hide user on this channel, Add as moderator
  const shown = ['Channel Activity', 'Go to channel', 'Pin message', 'Report', 'Remove', 'Put user in timeout',
    'Hide user on this channel', 'Add as moderator'];
  assert.deepEqual(shown.filter((t) => YT.MENU.delete.test(t)), ['Remove']);
  assert.deepEqual(shown.filter((t) => YT.MENU.timeout.test(t)), ['Put user in timeout']);
  assert.deepEqual(shown.filter((t) => YT.MENU.ban.test(t)), ['Hide user on this channel']);
});
