// Background part of the CrossChat extension. Two jobs:
//   1. carry questions and reports between X's Live Studio page, the streamer's own TikTok LIVE page, Facebook's
//      Live Producer, Instagram's Live producer and the CrossChat hub on this PC (hub/hub.py), which a page script
//      may not call directly;
//   2. post a reply typed in the CrossChat window to YouTube, X, TikTok, Facebook, Instagram and Rumble by typing it into those
//      sites' own chat boxes, as the accounts logged in to this browser. (Twitch and Kick replies go through their official APIs in
//      the hub; the extension never reads any login, cookie or token.)
const HUB = 'http://127.0.0.1:4466';
const LIMIT = { youtube: 200, x: 140, tiktok: 150, facebook: 8000, instagram: 2200, rumble: 200 };
const NAME = { youtube: 'YouTube', x: 'X', tiktok: 'TikTok', facebook: 'Facebook', instagram: 'Instagram', rumble: 'Rumble' };
const RUMBLE_CHAT = 'https://rumble.com/chat/popup/';
const PRODUCER = 'https://www.facebook.com/live/producer';
const INSTAGRAM = 'https://www.instagram.com/';
const hub = (path) => fetch(HUB + path, { cache: 'no-store' }).then((r) => r.json());

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  const from = sender.url || '';
  if (message.type === 'send' && from.startsWith(HUB + '/')) {
    post(message.data || {}, sender.tab).then(respond, () => respond(null));
    return true;   // the answer comes later
  }
  if (message.type === 'mod' && from.startsWith(HUB + '/')) {
    moderate(message.data || {}, sender.tab).then(respond, () => respond({ ok: false, why: 'it failed' }));
    return true;
  }
  if (message.type === 'tt-check' && from.startsWith('https://www.tiktok.com/')) {     // which account is the streamer's
    hub('/targets').then((t) => respond({ tiktok: t.tiktok || '', live: !!t.live, joins: t.tiktok_joins === true }), () => respond(null));
    return true;
  }
  if (message.type === 'tt-feed' && from.startsWith('https://www.tiktok.com/')) {
    hub('/tiktok/feed?' + new URLSearchParams(message.data || {}))
      .then((data) => respond({ reached: true, data }), () => respond({ reached: false }));
    return true;
  }
  if (message.type === 'yt-check' && from.startsWith(YT_CHAT)) {     // is the YouTube chat pop-out CrossChat opened still needed?
    stillNeeded(message, sender).then(respond, () => respond({ keep: true }));
    return true;
  }
  if (message.type === 'rm-check' && from.startsWith(RUMBLE_CHAT)) {     // which Rumble chat is the streamer's live?
    hub('/targets').then((t) => respond({ chat: t.live ? String(t.rumble_chat || '') : '' }), () => respond(null));
    return true;
  }
  if (message.type === 'fb-check' && from.startsWith(PRODUCER)) {     // is Facebook switched on, and is OBS live?
    hub('/targets').then((t) => respond({ facebook: !!t.facebook, live: !!t.live }), () => respond(null));
    return true;
  }
  if (message.type === 'fb-feed' && from.startsWith(PRODUCER)) {
    hub('/facebook/feed?' + new URLSearchParams(message.data || {}))
      .then((data) => respond({ reached: true, data }), () => respond({ reached: false }));
    return true;
  }
  if (message.type === 'ig-check' && from.startsWith(INSTAGRAM)) {     // is Instagram switched on, and is OBS live?
    hub('/targets').then((t) => respond({ instagram: !!t.instagram, live: !!t.live }), () => respond(null));
    return true;
  }
  if (message.type === 'ig-feed' && from.startsWith(INSTAGRAM)) {
    hub('/instagram/feed?' + new URLSearchParams(message.data || {}))
      .then((data) => respond({ reached: true, data }), () => respond({ reached: false }));
    return true;
  }
  if (['state', 'result', 'feed'].includes(message.type) && from.startsWith('https://studio.x.com/')) {
    hub(message.type === 'state' ? '/x/state' : '/x/' + message.type + '?' + new URLSearchParams(message.data))
      .then((data) => respond({ reached: true, data }), () => respond({ reached: false }));
    return true;
  }
});

// One reply, to one or several platforms. Answers {platform: {ok} or {ok: false, why}}.
async function post(data, tab) {
  const text = String(data.text || '').replace(/\s+/g, ' ').trim();     // one line: nothing typed can turn into a chat-server command
  const targets = await hub('/targets');
  const jobs = {
    youtube: () => youtube(targets.youtube_video, text, tab, !!data.dry),
    x: () => ask(chrome.tabs.query({ url: 'https://studio.x.com/live/*' }), { type: 'x-say', text }, 'the X livestream page is not open'),
    tiktok: () => ask(chrome.tabs.query({ url: 'https://www.tiktok.com/*' }), { type: 'tt-say', text }, 'the TikTok LIVE page is not open'),
    facebook: () => ask(chrome.tabs.query({ url: PRODUCER + '*' }), { type: 'fb-say', text }, 'Facebook Live Producer is not open'),
    instagram: () => ask(chrome.tabs.query({ url: INSTAGRAM + '*' }), { type: 'ig-say', text }, 'Instagram is not open'),
    rumble: () => ask(chrome.tabs.query({ url: RUMBLE_CHAT + '*' }), { type: 'rm-say', text }, 'the Rumble chat window is not open'),
  };
  const out = {};
  await Promise.all([...new Set(data.to || [])].map(async (p) => {
    if (!jobs[p]) out[p] = { ok: false, why: p === 'twitch' ? 'Connect Twitch in Settings to reply on Twitch' : 'not through the extension' };
    else if (!text) out[p] = { ok: false, why: 'nothing to send' };
    else if (data.dry && p !== 'youtube') out[p] = { ok: false, why: 'test mode, nothing is posted' };
    else if (text.length > LIMIT[p]) out[p] = { ok: false, why: NAME[p] + ' takes ' + LIMIT[p] + ' characters at most' };
    else out[p] = await jobs[p]().catch(() => ({ ok: false, why: 'it failed' }));
  }));
  return out;
}

// Moderation that has to go through the platform's own page: YouTube, deleting Facebook comments in Live Producer, and
// deleting or muting in Rumble's chat pop-out.
// The hub moderates Twitch and Kick itself through their APIs, and X offers nothing CrossChat can do.
async function moderate(data, tab) {
  if (data.p === 'facebook') {
    return ask(chrome.tabs.query({ url: PRODUCER + '*' }), { type: 'fb-mod', action: data.action, message_id: data.message_id }, 'Facebook Live Producer is not open');
  }
  if (data.p === 'rumble') {
    return ask(chrome.tabs.query({ url: RUMBLE_CHAT + '*' }), { type: 'rm-mod', action: data.action, name: String(data.name || ''), text: String(data.text || '') },
      'the Rumble chat window is not open');
  }
  if (data.p !== 'youtube') return { ok: false, why: 'only YouTube, Facebook and Rumble moderation go through the extension' };
  const { youtube_video: video } = await hub('/targets');
  if (!video) return { ok: false, why: 'the stream is not live on YouTube' };
  return ask(youtubeChatPage(video), { type: 'yt-mod', video, action: data.action, message_id: data.message_id, seconds: Number(data.seconds) || 0 },
    "YouTube's chat page could not be opened");
}

// YouTube moderates only on its own chat page: the copy embedded in the CrossChat window shows the channel owner no
// Remove, timeout or Hide user. So moderation goes to YouTube's chat pop-out for this live. When none is open, the
// extension opens one in a background tab of the browser (never in front, never a new window while one is open),
// marked with crosschat=1 in its address. That tab is used for every moderation of the live, and it closes itself
// once the live is over or CrossChat has closed (see yt-check); one for an earlier live is closed straight away.
const YT_CHAT = 'https://www.youtube.com/live_chat';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let opening = null;                            // { video, tabs }: the pop-out being opened, so two clicks open one

function chatPageFor(url, video) {
  try {
    const u = new URL(url);
    return u.origin === 'https://www.youtube.com' && u.pathname === '/live_chat' && !u.searchParams.has('embed_domain')
      && (video === undefined || u.searchParams.get('v') === video);
  } catch (e) {
    return false;
  }
}

// One CrossChat opened (not one the streamer opened by hand, which is never closed).
const ours = (url) => chatPageFor(url) && new URL(url).searchParams.get('crosschat') === '1';

function youtubeChatPage(video, wait = 1000, tries = 30) {
  if (opening && opening.video === video) return opening.tabs;
  const tabs = findOrOpenChatPage(video, wait, tries);
  opening = { video, tabs };
  const done = () => { if (opening && opening.tabs === tabs) opening = null; };
  tabs.then(done, done);
  return tabs;
}

async function findOrOpenChatPage(video, wait, tries) {
  const found = await chrome.tabs.query({ url: YT_CHAT + '*' });
  const stale = found.filter((t) => ours(t.url || '') && !chatPageFor(t.url, video)).map((t) => t.id);
  if (stale.length) await chrome.tabs.remove(stale).catch(() => {});
  const open = found.filter((t) => chatPageFor(t.url || t.pendingUrl || '', video));
  let tab = null;
  for (const t of open) {
    const ready = await chrome.tabs.sendMessage(t.id, { type: 'yt-ready', video }).catch(() => null);
    if (ready) return [t];
  }
  if (open.length) {         // open, but nothing answers there: it was loaded before the extension was (re)loaded
    tab = open[0];
    await chrome.tabs.reload(tab.id).catch(() => {});
  } else {
    const url = YT_CHAT + '?is_popout=1&v=' + encodeURIComponent(video) + '&crosschat=1';
    const windows = await chrome.windows.getAll({ windowTypes: ['normal'] }).catch(() => []);
    const where = windows.find((w) => w.focused) || windows[0];
    tab = where ? await chrome.tabs.create({ windowId: where.id, url, active: false })
      : (await chrome.windows.create({ url, focused: false, state: 'minimized' })).tabs[0];
  }
  for (let i = 0; i < tries; i++) {          // until YouTube's chat is on the page
    await sleep(wait);
    const ready = await chrome.tabs.sendMessage(tab.id, { type: 'yt-ready', video }).catch(() => null);
    if (ready && ready.ok) break;
  }
  return [tab];
}

// The pop-out CrossChat opened asks every half minute whether it is still needed: not once the live has ended or
// another one started, nor when CrossChat has been unreachable twice in a row (closed with OBS).
async function stillNeeded(message, sender) {
  if (!sender.tab || !ours(sender.url || '')) return { keep: true };
  const t = await hub('/targets').catch(() => null);
  const keep = t ? !!t.live && t.youtube_video === message.video : Number(message.misses) < 1;
  if (!keep) await chrome.tabs.remove(sender.tab.id).catch(() => {});
  return { keep, reached: !!t };
}

if (typeof module === 'object' && module.exports) module.exports = { moderate, chatPageFor, youtubeChatPage, stillNeeded };   // Node (the tests)

// Hand the message to the page script in one of these tabs; the first one that manages it wins.
async function ask(tabs, message, nobody) {
  let last = null;
  for (const tab of await tabs) {
    const answer = await chrome.tabs.sendMessage(tab.id, message).catch(() => null);
    if (answer && answer.ok) return answer;
    last = answer || last;
  }
  return last || { ok: false, why: nobody };
}

// YouTube: its own chat box does the sending. That box sits (out of sight) inside the CrossChat window;
// a YouTube chat pop-out open in another tab works too.
async function youtube(video, text, tab, dry) {
  if (!video) return { ok: false, why: 'the stream is not live on YouTube' };
  const tabs = chrome.tabs.query({ url: 'https://www.youtube.com/live_chat*' }).then((found) => (tab ? [tab, ...found] : found));
  const answer = await ask(tabs, { type: 'yt-say', text, video, dry }, 'YouTube chat is not loaded yet');
  // test mode: the chat box is filled and emptied again, and nothing is sent
  return dry && answer.dry ? { ok: false, why: answer.ok ? 'test mode: YouTube took the text, nothing was posted' : 'test mode: ' + answer.why } : answer;
}
