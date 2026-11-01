// Tests for extension/facebook.js: which link of a Live Producer comment gives its id and the commenter's name.
// Run: node --test "tests/js/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const FB = require('../../extension/facebook.js');

const link = (text, id) => ({ textContent: text, href: 'https://www.facebook.com/profile.php?id=1&comment_id=' + id });
const article = (links) => ({ querySelectorAll: (s) => (s === 'a[href*="comment_id="]' ? links : []) });

test("a viewer's comment: the picture link comes first and has no text, the name link is used", () => {
  // as Live Producer showed a Page's comment on 31 October 2026: <a aria-hidden="true"><svg/></a>, then the name
  const picture = link('', 'Y29tbWVudDox');
  const name = link('Tech I.T.', 'Y29tbWVudDox');
  assert.equal(FB.nameLink(article([picture, name])), name);
});

test("the streamer's own comment (the name link first) still works", () => {
  const name = link('Randy Northrup', 'abc');
  assert.equal(FB.nameLink(article([name])), name);
});

test('a comment with no named link yet (still posting) is skipped', () => {
  assert.equal(FB.nameLink(article([link('  ', 'x')])), null);
  assert.equal(FB.nameLink(article([])), null);
});
