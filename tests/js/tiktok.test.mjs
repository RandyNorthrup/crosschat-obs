// Tests for extension/tiktok-rows.js: what each row of TikTok's LIVE chat becomes, and one alert per gift streak.
// Run: node --test "tests/js/*.test.mjs"   (tests/browser/tiktok_page.cjs runs the same rows on a real page)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { loadExtension } from './extension-files.mjs';

const require = createRequire(import.meta.url);
const TT = loadExtension('common.js', 'tiktok-rows.js').CrossChatTikTokRows;
const ROWS = require('../fixtures/tiktok_rows.json').rows;

for (const row of ROWS) {
  test('row: ' + row.case, () => {
    assert.deepEqual(TT.classify(row.parts), row.expect);
  });
}

test('a marked chat row that is no known event keeps its words', () => {
  const r = TT.classify({ e2e: 'chat-message', hints: 'DivSystemMessage', name: 'mod.mo', rest: 'pinned a comment' });
  assert.deepEqual(r, { kind: 'chat', name: 'mod.mo', text: 'pinned a comment' });
});

test('long names, gift names and huge counts are cut down', () => {
  const r = TT.classify({ e2e: 'gift-message', name: 'n'.repeat(80), rest: 'sent ' + 'g'.repeat(80) + ' ×999999', giftImage: true });
  assert.equal(r.name.length, 60);
  assert.equal(r.gift.length, 40);
  assert.ok(r.count >= 1 && r.count < 100000);
});

test('a gift row without a count or a gift picture is not a gift', () => {
  assert.equal(TT.classify({ e2e: 'gift-message', name: 'a.b', rest: 'sent Rose' }), null);
});

test('one gift streak is one alert, with its last count', () => {
  const out = [];
  const s = TT.giftStreaks((g, count) => out.push(g.gift + ' ×' + count));
  const rose = (count) => ({ kind: 'gift', name: 'pixel.pal', gift: 'Rose', count });
  s.see(rose(1), 0); s.see(rose(2), 400); s.see(rose(3), 800);
  s.flush(800 + TT.GIFT_QUIET - 1, false);
  assert.deepEqual(out, []);                                   // still rising, maybe
  s.flush(800 + TT.GIFT_QUIET, false);
  assert.deepEqual(out, ['Rose ×3']);
  s.flush(99999, false);
  assert.deepEqual(out, ['Rose ×3']);                          // not twice
});

test('a combo that rises again after its alert adds only the gifts since', () => {
  const out = [];
  const s = TT.giftStreaks((g, count) => out.push(count));
  const rose = (count) => ({ kind: 'gift', name: 'slow.sam', gift: 'Rose', count });
  const row = {}, another = {};
  s.see(rose(1), 0, row); s.see(rose(3), 1000, row);
  s.flush(1000 + TT.GIFT_QUIET, false);
  s.see(rose(4), 8000, row); s.see(rose(5), 9000, row);      // the same row keeps counting, slowly
  s.flush(9000 + TT.GIFT_QUIET, false);
  assert.deepEqual(out, [3, 2]);                               // 5 Roses in all, never 3 + 5
  s.see(rose(10), 20000, another);                             // a new row: a new send of 10, all counted
  s.flush(20000 + TT.GIFT_QUIET, false);
  assert.deepEqual(out, [3, 2, 10]);
  s.see(rose(11), 9000 + TT.GIFT_AGAIN + 40000, another);     // the old row, much later: a new streak in full
  s.flush(Infinity, true);
  assert.deepEqual(out, [3, 2, 10, 11]);
});

test('separate gifts are never merged or lost', () => {
  const out = [];
  const s = TT.giftStreaks((g, count) => out.push(g.name + ':' + g.gift + ' ×' + count));
  s.see({ name: 'a', gift: 'Rose', count: 1 }, 0);
  s.see({ name: 'a', gift: 'Galaxy', count: 1 }, 10);         // another gift from the same viewer
  s.see({ name: 'b', gift: 'Rose', count: 1 }, 20);           // the same gift from someone else
  s.see({ name: 'a', gift: 'Rose', count: 1 }, 30);           // a's Rose again from ×1: a new streak
  assert.deepEqual(out, ['a:Rose ×1']);
  s.flush(100, true);
  assert.deepEqual(out.sort(), ['a:Galaxy ×1', 'a:Rose ×1', 'a:Rose ×1', 'b:Rose ×1']);
});
