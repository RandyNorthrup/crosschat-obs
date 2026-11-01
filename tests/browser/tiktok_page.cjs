// extension/tiktok.js on a real browser page built from tests/fixtures/tiktok_rows.json (no TikTok, no network).
// Needs Playwright and Edge: set PLAYWRIGHT to Playwright's folder if it isn't installed here.
//   node tests/browser/tiktok_page.cjs
const path = require('path');
const fs = require('fs');
let chromium;
try { ({ chromium } = require(process.env.PLAYWRIGHT || 'playwright')); } catch (e) {
  console.log('SKIPPED: Playwright not found (set PLAYWRIGHT to its folder)');
  process.exit(0);
}
const ROOT = path.join(__dirname, '..', '..');
const SCRIPT = fs.readFileSync(path.join(ROOT, 'extension', 'tiktok.js'), 'utf8');
const ROWS = JSON.parse(fs.readFileSync(path.join(ROOT, 'tests', 'fixtures', 'tiktok_rows.json'), 'utf8')).rows;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let failed = 0;
const check = (name, ok, info) => { console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok || info === undefined ? '' : '  ' + JSON.stringify(info))); if (!ok) failed++; };

const PAGE = `<!doctype html><meta charset="utf-8"><body>
<div data-e2e="live-header-container"><a data-e2e="room-header-anchor-name">Sunny Daze</a></div>
<div data-e2e="public-screen-container"><div data-e2e="live-chat-container">
  <div><span>Viewers</span> · <span>1.2K</span></div>
  <div id="list"></div>
  <div data-e2e="live-chat-input-container">
    <div data-e2e="room-chat-input-field" contenteditable="plaintext-only"></div>
    <button data-e2e="room-chat-send-btn">Send</button>
  </div>
</div></div>
<script>
  window.addRow = (html) => { const t = document.createElement('template'); t.innerHTML = html; const row = t.content.firstElementChild; document.getElementById('list').append(row); return document.getElementById('list').children.length - 1; };
  window.setRow = (i, html) => { const t = document.createElement('template'); t.innerHTML = html; const now = t.content.firstElementChild;
    const row = document.getElementById('list').children[i]; row.className = now.className; row.setAttribute('data-e2e', now.getAttribute('data-e2e')); row.innerHTML = now.innerHTML; };
</script>`;

// A page at TikTok's address with the extension's messaging faked: the hub's answers come from `hub`.
async function open(ctx, where, hub) {
  const page = await ctx.newPage();
  const feeds = [];
  await page.exposeFunction('__feed', (d) => feeds.push(d));
  await page.exposeFunction('__answer', () => hub.answer(feeds.length));
  await page.addInitScript(([check]) => {
    let listener = null;
    window.chrome = { runtime: {
      lastError: null,
      sendMessage(message, reply) {
        if (message.type === 'tt-check') setTimeout(() => reply(check), 5);
        else if (message.type === 'tt-feed') { window.__feed(message.data).then(() => window.__answer()).then((a) => reply(a)); }
      },
      onMessage: { addListener(fn) { listener = fn; } },
    } };
  }, [hub.check]);
  await page.route('https://www.tiktok.com/**', (route) => route.fulfill({ contentType: 'text/html', body: PAGE }));
  await page.goto('https://www.tiktok.com' + where);
  await page.addScriptTag({ content: SCRIPT });
  return { page, feeds, items: () => feeds.flatMap((f) => JSON.parse(f.lines || '[]')) };
}

const mineHub = (check, failFirst) => ({ check, answer: (n) => (failFirst && n === 1 ? { reached: false } : { reached: true, data: { mine: true } }) });

(async () => {
  const browser = await chromium.launch({ channel: 'msedge' });
  const ctx = await browser.newContext();
  const errs = [];

  // the streamer's own page, joins wanted; the first answer from the hub is lost (it must be sent again, same ids)
  const own = await open(ctx, '/@sunny.daze/live', mineHub({ tiktok: 'sunny.daze', live: true, joins: true }, true));
  own.page.on('pageerror', (e) => errs.push(e.message));
  for (const row of ROWS) await own.page.evaluate((h) => addRow(h), row.html);
  await sleep(7500);                                   // gifts wait out the streak hold (4.5 s) first
  const got = own.items();
  for (const row of ROWS) {
    const want = row.expect;
    const found = got.filter((i) => i.name === (want || {}).name && (i.kind || 'chat') === (want || {}).kind
      && (want.kind !== 'chat' || i.text === want.text) && (want.kind !== 'gift' || (i.gift === want.gift && i.count === want.count)));
    if (want) check('passed on: ' + row.case, found.length >= 1, got);
  }
  check("TikTok's welcome notice is not passed on", !got.some((i) => /Welcome/.test(i.text || '')), got);
  const ids = got.map((i) => i.id);
  check('a lost answer is sent again with the same ids', new Set(ids).size < ids.length && own.feeds.length >= 2, own.feeds.length);
  const before = own.items().length;
  await sleep(2000);
  check('nothing is sent twice once the hub has it', own.items().length === before, own.items().slice(before));

  // a gift combo counted up in place: one item, with the last count, once the count stops rising
  const combo = (n) => `<div data-e2e="chat-message" class="css-4k3j-DivGiftMessage"><span data-e2e="message-owner-name" title="combo.carl">combo.carl</span><span>sent Rose</span><img alt="Rose" src="https://p16-webcast.tiktokcdn.com/img/rose~tplv-obj.png"><span class="css-2z1x-SpanGiftCount">×${n}</span></div>`;
  const at = await own.page.evaluate((h) => addRow(h), combo(1));
  for (let n = 2; n <= 7; n++) { await sleep(400); await own.page.evaluate(([i, h]) => setRow(i, h), [at, combo(n)]); }
  await sleep(1500);
  check('a rising combo is held back', !own.items().some((i) => i.name === 'combo.carl'));
  await sleep(6500);
  const gifts = own.items().filter((i) => i.name === 'combo.carl');
  check('one gift streak, one item, last count', gifts.length === 1 && gifts[0].count === 7 && gifts[0].gift === 'Rose',
    { gifts, last: own.items().slice(-3), row: await own.page.evaluate((i) => document.getElementById('list').children[i].outerHTML, at) });

  // TikTok reuses a row's element for a later line: the new line still counts
  await own.page.evaluate(([i, h]) => setRow(i, h), [at, '<div data-e2e="chat-message" class="css-1q2w-DivChatMessage"><span data-e2e="message-owner-name" title="late.lin">late.lin</span><span>reused row</span></div>']);
  await sleep(2000);
  check('a reused row element is read again', own.items().some((i) => i.name === 'late.lin' && i.text === 'reused row'), own.items().slice(-3));

  // the streamer's own events aren't alerts; their chat is marked as theirs
  await own.page.evaluate((h) => addRow(h), '<div data-e2e="social-message" class="DivSocialMessage"><span data-e2e="message-owner-name" title="Sunny Daze">Sunny Daze</span><span>shared the LIVE</span></div>');
  await sleep(2000);
  check("the streamer's own share is not passed on", !own.items().some((i) => i.name === 'Sunny Daze' && i.kind === 'share'));

  // joins not wanted: none are sent at all
  const quiet = await open(ctx, '/@sunny.daze/live', mineHub({ tiktok: 'sunny.daze', live: true, joins: false }));
  await quiet.page.evaluate((h) => addRow(h), ROWS.find((r) => r.expect && r.expect.kind === 'join').html);
  await quiet.page.evaluate((h) => addRow(h), ROWS.find((r) => r.expect && r.expect.kind === 'follow').html);
  await sleep(2500);
  check('joins are not sent unless wanted', !quiet.items().some((i) => i.kind === 'join') && quiet.items().some((i) => i.kind === 'follow'), quiet.items());

  // someone else's LIVE, or not streaming: nothing is read
  const other = await open(ctx, '/@someone.else/live', mineHub({ tiktok: 'sunny.daze', live: true, joins: true }));
  for (const row of ROWS) await other.page.evaluate((h) => addRow(h), row.html);
  await sleep(2500);
  check("someone else's LIVE: nothing passed on", other.feeds.length === 0, other.feeds);
  const idle = await open(ctx, '/@sunny.daze/live', mineHub({ tiktok: 'sunny.daze', live: false, joins: true }));
  for (const row of ROWS) await idle.page.evaluate((h) => addRow(h), row.html);
  await sleep(2500);
  check('not streaming: nothing passed on', idle.feeds.length === 0, idle.feeds);

  // a burst: every request stays within the hub's limits (50 lines, small enough for one request)
  await own.page.evaluate(() => { for (let i = 0; i < 120; i++) addRow('<div data-e2e="chat-message"><span data-e2e="message-owner-name" title="fan' + i + '">fan' + i + '</span><span>' + (i % 2 ? '🎉'.repeat(140) : 'hi') + '</span></div>'); });
  await sleep(4000);
  const counts = own.feeds.map((f) => JSON.parse(f.lines || '[]').length);
  const sizes = own.feeds.map((f) => encodeURIComponent(new URLSearchParams(f).toString()).length);
  check('a burst arrives in full', own.items().filter((i) => /^fan\d+$/.test(i.name)).length === 120);
  check('no request carries more than 50 lines', Math.max(...counts) <= 50, Math.max(...counts));
  check('every request stays small', Math.max(...sizes) < 15000, Math.max(...sizes));

  check('no page errors', errs.length === 0, errs);
  await browser.close();
  console.log(failed ? failed + ' FAILED' : 'ALL PASSED');
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
