// Every page script of extension/manifest.json, loaded the way Chrome loads it: only the files its entry lists, in that
// order. A script that used a helper from a file its entry doesn't list would stop right here.
// Run: node --test "tests/js/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { openPage } from './fake-page.mjs';

const manifest = JSON.parse(readFileSync(new URL('../../extension/manifest.json', import.meta.url), 'utf8'));

for (const entry of manifest.content_scripts) {
  test('loads from its manifest entry: ' + entry.js.join(' + '), async () => {
    const url = entry.matches[0].replaceAll('*', '');
    const page = await openPage('tests/js/blank.html', [], { url });
    const listeners = [];
    page.window.chrome = { runtime: {
      lastError: null, getManifest: () => ({ version: '1.9.0' }),
      onMessage: { addListener: (fn) => listeners.push(fn) },
      sendMessage: (m, reply) => { if (reply) reply(null); },
    } };
    entry.js.forEach((file) => page.script('extension/' + file));
    await page.settle();
    await page.advance(3000);                                 // their timers run too: a first tick of each
    if (entry.js.includes('common.js')) assert.equal(typeof page.window.CrossChatCommon.waitFor, 'function');
    if (entry.world === 'MAIN') assert.equal(page.window.CrossChatCommon, undefined);
  });
}

test('every script that reads helpers from common.js is loaded after it', () => {
  for (const entry of manifest.content_scripts) {
    const at = entry.js.indexOf('common.js');
    entry.js.forEach((file, i) => {
      if (readFileSync(new URL('../../extension/' + file, import.meta.url), 'utf8').includes('CrossChatCommon') && file !== 'common.js') {
        assert.ok(at >= 0 && at < i, file + ' needs common.js before it in its manifest entry');
      }
    });
  }
});
