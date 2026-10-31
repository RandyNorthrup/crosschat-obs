// Runs inside YouTube's live chat page (the copy that sits out of sight in the CrossChat window, or a chat
// pop-out). Types a reply that comes from the CrossChat window into YouTube's own chat box and sends it.
// It only acts for the video the CrossChat hub names, so it can never post into somebody else's chat.
(() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const box = () => document.querySelector('yt-live-chat-text-input-field-renderer #input[contenteditable], #input[contenteditable]');
  const sendButton = () => document.querySelector('#send-button button');

  async function say(line, dry) {
    const input = box();
    if (!input) {
      const closed = document.querySelector('yt-live-chat-restricted-participation-renderer');
      return { ok: false, why: closed ? 'YouTube is not letting this account chat here' : 'YouTube chat is not signed in inside the chat window' };
    }
    input.focus();
    input.textContent = line;
    input.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, inputType: 'insertText', data: line }));
    await sleep(300);
    const send = sendButton();
    const ready = !!send && !send.disabled && send.getAttribute('aria-disabled') !== 'true';
    if (dry || !ready) {                       // dry: a test that fills the box and empties it again, sending nothing
      input.textContent = '';
      input.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, inputType: 'deleteContentBackward' }));
      return dry ? { ok: ready, dry: true, why: ready ? '' : 'the Send button stayed off' } : { ok: false, why: 'YouTube would not take the message' };
    }
    send.click();
    for (let i = 0; i < 25; i++) {
      await sleep(200);
      if (!(input.textContent || '').trim()) return { ok: true };
    }
    return { ok: false, why: 'YouTube did not send it' };
  }

  // Moderation through YouTube's own message menu, as the signed-in channel owner or moderator would do it by hand.
  const text = (el) => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const MENU = { delete: /^(remove|delete)$/i, timeout: /^put user in timeout$/i, ban: /^hide user on this channel$/i };
  const CONFIRM = /^(hide|hide user|remove|delete|put in timeout|confirm|yes)$/i;

  async function moderate(action, messageId) {
    if (!MENU[action]) return { ok: false, why: 'YouTube has no ' + action + ' in its chat menu' };
    const item = [...document.querySelectorAll('yt-live-chat-text-message-renderer, yt-live-chat-paid-message-renderer')]
      .find((el) => el.id === messageId);
    if (!item) return { ok: false, why: "that message is no longer in YouTube's chat" };
    item.scrollIntoView({ block: 'center' });
    item.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
    await sleep(200);
    const opener = item.querySelector('#menu-button button, #menu button, button[aria-label]');
    if (!opener) return { ok: false, why: "YouTube's message menu did not appear" };
    opener.click();
    let choice = null;
    for (let i = 0; i < 15 && !choice; i++) {
      await sleep(200);
      choice = [...document.querySelectorAll('ytd-menu-service-item-renderer, tp-yt-paper-item, yt-list-item-view-model')]
        .find((el) => MENU[action].test(text(el)));
    }
    if (!choice) {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      return { ok: false, why: 'YouTube did not offer that here (is this account the channel owner or a moderator?)' };
    }
    choice.click();
    for (let i = 0; i < 10; i++) {                      // hiding a user asks "are you sure?" first
      await sleep(200);
      const yes = [...document.querySelectorAll('yt-confirm-dialog-renderer button, tp-yt-paper-dialog button')].find((b) => CONFIRM.test(text(b)));
      if (yes) { yes.click(); break; }
    }
    return { ok: true };
  }

  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (!['yt-say', 'yt-mod'].includes(message.type) || !message.video) return;
    if (new URLSearchParams(location.search).get('v') !== message.video) return;
    if (message.type === 'yt-say') say(String(message.text || ''), !!message.dry).then(respond);
    else moderate(String(message.action || ''), String(message.message_id || '')).then(respond, () => respond({ ok: false, why: 'it failed' }));
    return true;   // the answer comes later
  });
})();
