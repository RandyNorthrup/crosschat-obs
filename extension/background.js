// Background part of the CrossChat extension. Two jobs:
//   1. carry questions and reports between X's Live Studio page, the streamer's own TikTok LIVE page, Facebook's
//      Live Producer and the CrossChat hub on this PC (hub/hub.py), which a page script may not call directly;
//   2. post a reply typed in the CrossChat window to YouTube, X, TikTok, Facebook and Rumble by typing it into those
//      sites' own chat boxes, as the accounts logged in to this browser. (Twitch and Kick replies go through their official APIs in
//      the hub; the extension never reads any login, cookie or token.)
const HUB = 'http://127.0.0.1:4466';
const LIMIT = { youtube: 200, x: 140, tiktok: 150, facebook: 8000, rumble: 200 };
const NAME = { youtube: 'YouTube', x: 'X', tiktok: 'TikTok', facebook: 'Facebook', rumble: 'Rumble' };
const RUMBLE_CHAT = 'https://rumble.com/chat/popup/';
const PRODUCER = 'https://www.facebook.com/live/producer';
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
    hub('/targets').then((t) => respond({ tiktok: t.tiktok || '', live: !!t.live }), () => respond(null));
    return true;
  }
  if (message.type === 'tt-feed' && from.startsWith('https://www.tiktok.com/')) {
    hub('/tiktok/feed?' + new URLSearchParams(message.data || {}))
      .then((data) => respond({ reached: true, data }), () => respond({ reached: false }));
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

// Moderation that has to go through the platform's own page: YouTube, and deleting Facebook comments in Live Producer.
// The hub moderates Twitch and Kick itself through their APIs, and X offers nothing CrossChat can do.
async function moderate(data, tab) {
  if (data.p === 'facebook') {
    return ask(chrome.tabs.query({ url: PRODUCER + '*' }), { type: 'fb-mod', action: data.action, message_id: data.message_id }, 'Facebook Live Producer is not open');
  }
  if (data.p !== 'youtube') return { ok: false, why: 'only YouTube and Facebook moderation go through the extension' };
  const { youtube_video: video } = await hub('/targets');
  if (!video) return { ok: false, why: 'the stream is not live on YouTube' };
  const tabs = chrome.tabs.query({ url: 'https://www.youtube.com/live_chat*' }).then((found) => (tab ? [tab, ...found] : found));
  return ask(tabs, { type: 'yt-mod', video, action: data.action, message_id: data.message_id }, 'YouTube chat is not loaded yet');
}

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
