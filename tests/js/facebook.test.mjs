// Tests for extension/facebook-comments.js: which link of a Live Producer comment gives its id and the commenter's name.
// Run: node --test "tests/js/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadExtension } from './extension-files.mjs';

const FB = loadExtension('common.js', 'facebook-comments.js').CrossChatFacebookComments;

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

test("a comment's words lose Facebook's separator dot and its \"Posting…\", nothing else", () => {
  assert.equal(FB.words(' · hello there '), 'hello there');       // as CrossChat showed a Page's comment on 31 October 2026
  assert.equal(FB.words('• hi'), 'hi');
  assert.equal(FB.words('hello Posting…'), 'hello');
  assert.equal(FB.words('hello Posting...'), 'hello');
  assert.equal(FB.words('· · twice'), '· twice');                  // only Facebook's one separator goes
  assert.equal(FB.words('a · b'), 'a · b');                        // a dot inside the comment stays
  assert.equal(FB.words('-1 for that'), '-1 for that');
});

test('a comment with no named link yet (still posting) is skipped', () => {
  assert.equal(FB.nameLink(article([link('  ', 'x')])), null);
  assert.equal(FB.nameLink(article([])), null);
});
