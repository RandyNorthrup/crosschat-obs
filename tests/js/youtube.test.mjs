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

test('the menu entries CrossChat picks are the ones YouTube shows the channel owner', () => {
  // the owner's menu on that live: Channel Activity, Go to channel, Pin message, Report, Remove, Put user in timeout,
  // Hide user on this channel, Add as moderator
  const shown = ['Channel Activity', 'Go to channel', 'Pin message', 'Report', 'Remove', 'Put user in timeout',
    'Hide user on this channel', 'Add as moderator'];
  assert.deepEqual(shown.filter((t) => YT.MENU.delete.test(t)), ['Remove']);
  assert.deepEqual(shown.filter((t) => YT.MENU.timeout.test(t)), ['Put user in timeout']);
  assert.deepEqual(shown.filter((t) => YT.MENU.ban.test(t)), ['Hide user on this channel']);
});
