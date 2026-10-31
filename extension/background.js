// Background part of the CrossChat extension. Two jobs:
//   1. carry questions and reports between X's Live Studio page and the CrossChat hub on this PC (hub/hub.py),
//      which a page script may not call directly;
//   2. post a reply typed in the CrossChat window to Twitch, YouTube and X, as the accounts logged in to
//      this browser.
const HUB = 'http://127.0.0.1:4466';
const LIMIT = { twitch: 500, youtube: 200, x: 140 };
const NAME = { twitch: 'Twitch', youtube: 'YouTube', x: 'X' };
const hub = (path) => fetch(HUB + path, { cache: 'no-store' }).then((r) => r.json());

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  const from = sender.url || '';
  if (message.type === 'send' && from.startsWith(HUB + '/')) {
    post(message.data || {}, sender.tab).then(respond, () => respond(null));
    return true;   // the answer comes later
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
  const reply = data.reply || {};
  const targets = await hub('/targets');
  // A threaded Twitch reply gets its "@name" from Twitch, so the one the CrossChat window put in front comes off.
  const threaded = reply.p === 'twitch' && text.toLowerCase().startsWith('@' + String(reply.name || '').toLowerCase() + ' ');
  const jobs = {
    twitch: () => twitch(targets.twitch, threaded ? text.slice(String(reply.name).length + 2) : text, reply.p === 'twitch' ? reply.id : ''),
    youtube: () => youtube(targets.youtube_video, text, tab, !!data.dry),
    x: () => ask(chrome.tabs.query({ url: 'https://studio.x.com/live/*' }), { type: 'x-say', text }, 'the X livestream page is not open'),
  };
  const out = {};
  await Promise.all([...new Set(data.to || [])].filter((p) => jobs[p]).map(async (p) => {
    if (!text) out[p] = { ok: false, why: 'nothing to send' };
    else if (data.dry && p !== 'youtube') out[p] = { ok: false, why: 'test mode, nothing is posted' };
    else if (text.length > LIMIT[p]) out[p] = { ok: false, why: NAME[p] + ' takes ' + LIMIT[p] + ' characters at most' };
    else out[p] = await jobs[p]().catch(() => ({ ok: false, why: 'it failed' }));
  }));
  return out;
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

// Twitch: the same chat connection the Twitch site opens, signed in with this browser's Twitch login.
// The login is read here, used for this one connection to Twitch, and goes nowhere else.
async function twitch(channel, text, parent) {
  channel = String(channel || '').toLowerCase().replace(/[^a-z0-9_]/g, '');
  const [token, login] = await Promise.all(['auth-token', 'login'].map((name) => chrome.cookies.get({ url: 'https://www.twitch.tv', name })));
  if (!channel) return { ok: false, why: 'no Twitch channel is set' };
  if (!token || !login) return { ok: false, why: 'this browser is not logged in to Twitch' };
  return new Promise((resolve) => {
    const ws = new WebSocket('wss://irc-ws.chat.twitch.tv:443');
    let sent = false;
    const done = (answer) => {
      clearTimeout(timer);
      ws.onmessage = ws.onclose = ws.onerror = null;
      try { ws.close(); } catch (e) { /* already closed */ }
      resolve(answer);
    };
    const timer = setTimeout(() => done({ ok: false, why: 'Twitch did not answer' }), 12000);
    ws.onerror = ws.onclose = () => done({ ok: false, why: 'could not reach Twitch chat' });
    ws.onopen = () => {
      ws.send('CAP REQ :twitch.tv/tags twitch.tv/commands');
      ws.send('PASS oauth:' + token.value);
      ws.send('NICK ' + login.value);
    };
    ws.onmessage = (event) => {
      for (const line of String(event.data).split('\r\n')) {
        const [, tags, command, rest] = /^(?:@(\S+) )?(?::\S+ )?(\S+)(?: (.*))?$/.exec(line) || [];
        if (command === 'PING') ws.send('PONG :tmi.twitch.tv');
        else if (command === '001') ws.send('JOIN #' + channel);
        else if (command === 'NOTICE') done({ ok: false, why: (rest || '').replace(/^\S+ :/, '') || 'Twitch refused it' });
        else if ((command === 'USERSTATE' || command === 'ROOMSTATE') && !sent) {          // in the channel: say it
          sent = true;
          const thread = /^[\w-]+$/.test(parent || '') ? '@reply-parent-msg-id=' + parent + ' ' : '';
          ws.send(thread + 'PRIVMSG #' + channel + ' :' + text);
        } else if (command === 'USERSTATE' && /(^|;)id=/.test(tags || '')) done({ ok: true });   // Twitch took the message
      }
    };
  });
}
