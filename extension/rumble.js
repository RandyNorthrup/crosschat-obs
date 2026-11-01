// In the Rumble chat pop-out of the streamer's own live (CrossChat opens it once Rumble's official API says the live
// has started), this script:
//   - types a reply from the CrossChat window into Rumble's chat box and sends it;
//   - deletes a message or mutes its sender when the streamer chooses that in the CrossChat window, through the same
//     "Moderate this comment" menu Rumble shows the streamer.
// Reading Rumble chat doesn't happen here: CrossChat gets it from Rumble's official Live Stream API. The script first
// asks CrossChat which chat is the streamer's, and does nothing in any other. It never presses the Rant button (Rants
// cost money) and never touches the Rumble login.
(() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const ask = (type, data) => new Promise((r) => {
    try { chrome.runtime.sendMessage({ type, data }, (a) => r(chrome.runtime.lastError ? null : a)); } catch (e) { r(null); }
  });
  const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim();
  const chatHere = () => (/^\/chat\/popup\/(\d+)/.exec(location.pathname) || [])[1] || '';
  const mine = async () => { const answer = await ask('rm-check'); return !!(answer && answer.chat && answer.chat === chatHere()); };
  async function until(find, ms) {
    for (let waited = 0; waited <= ms; waited += 100) {
      const found = find();
      if (found) return found;
      await sleep(100);
    }
    return null;
  }

  async function say(text) {
    if (!(await mine())) return { ok: false, why: "this isn't your live's Rumble chat" };
    const box = document.getElementById('chat-message-text-input');
    if (!box) return { ok: false, why: 'sign in to Rumble in this browser to reply there' };
    // Typed the way a person types (Rumble switches its Send button on from those events); set directly only if that fails.
    box.focus();
    box.select();
    document.execCommand('insertText', false, text);
    if (box.value !== text) {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(box, text);
      box.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
    }
    box.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: ' ' }));
    const send = await until(() => {
      const b = document.querySelector('button.chat--send[name="send"]');    // (never the Rant button next to it)
      return b && !b.disabled ? b : null;
    }, 1500);
    if (!send) return { ok: false, why: 'Rumble would not take the message' };
    send.click();
    for (let i = 0; i < 25; i++) {
      await sleep(200);
      if (!box.isConnected || box.value === '') return { ok: true };
    }
    return { ok: false, why: 'Rumble did not send it' };
  }

  // The menu entry for each action: Rumble's own buttons in its "Moderate this comment" menu.
  const BUTTON = { delete: '.js-btn-delete-current', timeout: '.js-btn-mute-current-5', mute: '.js-btn-mute-current', ban: '.js-btn-mute-for-account' };

  // A chat line's own words: its text without the name, avatar and menu (those are buttons and links in Rumble's rows).
  function words(row) {
    const copy = row.cloneNode(true);
    copy.querySelectorAll('button, a, [role="button"]').forEach((n) => n.remove());
    return clean(copy.textContent);
  }

  // The newest chat line from this name with these words that Rumble still shows (and offers its menu for).
  function line(name, text) {
    const rows = [...document.querySelectorAll('.js-chat-history-item')].reverse();
    return rows.find((row) => {
      const who = row.querySelector('.chat-history--username');
      return who && clean(who.textContent) === name && row.querySelector('.js-moderate-btn') && words(row) === text;
    }) || null;
  }

  // The last message Rumble showed in its notice at the bottom, if any, to pass on as the answer.
  const notice = () => [...document.querySelectorAll('[role="alert"], [class*="toast"], [class*="notification"]')]
    .map((n) => clean(n.textContent)).filter(Boolean).pop() || '';

  async function moderate(action, name, text) {
    if (!BUTTON[action]) return { ok: false, why: "Rumble can't do that from CrossChat" };
    if (!(await mine())) return { ok: false, why: "this isn't your live's Rumble chat" };
    name = clean(name); text = clean(text);
    const row = name && text ? line(name, text) : null;
    if (!row) return { ok: false, why: 'that message is no longer in the Rumble chat window' };
    const before = notice();
    row.querySelector('.js-moderate-btn').click();
    const button = await until(() => [...document.querySelectorAll(BUTTON[action])].find((b) => b.offsetParent !== null) || null, 3000);
    if (!button) return { ok: false, why: 'Rumble showed no moderation menu (is this the account that is live?)' };
    // Rumble asks "Would you like to delete this message?" with the browser's own question box; rumble-confirm.js (which
    // runs in the page itself) answers yes to that one question, once, for this click only.
    if (action === 'delete') document.dispatchEvent(new CustomEvent('crosschat-rumble-confirm'));
    button.click();
    if (action === 'delete') {
      const gone = await until(() => !row.isConnected || /removed by moderator/i.test(row.textContent), 5000);
      return gone ? { ok: true } : { ok: false, why: 'Rumble did not delete it' };
    }
    const said = await until(() => { const n = notice(); return n && n !== before ? n : null; }, 5000);
    if (said && /fail|error|not allowed|can't|cannot/i.test(said)) return { ok: false, why: said.slice(0, 160) };
    return said ? { ok: true } : { ok: false, why: 'Rumble did not confirm the mute' };
  }

  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (message.type === 'rm-say') say(String(message.text || '')).then(respond, () => respond({ ok: false, why: 'it failed' }));
    else if (message.type === 'rm-mod') moderate(String(message.action || ''), message.name, message.text).then(respond, () => respond({ ok: false, why: 'it failed' }));
    else return;
    return true;   // the answer comes later
  });
})();
