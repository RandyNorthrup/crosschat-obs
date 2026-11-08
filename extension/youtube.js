// Runs inside YouTube's live chat page (the copy that sits out of sight in the CrossChat window, or a chat
// pop-out). Types a reply that comes from the CrossChat window into YouTube's own chat box and sends it.
// It only acts for the video the CrossChat hub names, so it can never post into somebody else's chat.
(() => {
  const { sleep, ask, waitFor } = globalThis.CrossChatCommon;
  const { text, menuButton, MENU, timeoutDialog, embedded, shown } = globalThis.CrossChatYouTubeMenu;
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
    return (await waitFor(() => !(input.textContent || '').trim(), 5000, 200)) ? { ok: true } : { ok: false, why: 'YouTube did not send it' };
  }

  // Moderation through YouTube's own message menu, as the signed-in channel owner or moderator would do it by hand.
  // Only YouTube's own chat page offers it: in the copy embedded in the CrossChat window (embed_domain=...) the menu
  // has just "Go to channel" and "Pin message", so the extension opens the chat pop-out for moderating.
  async function moderate(action, messageId, seconds) {
    if (!MENU[action]) return { ok: false, why: 'YouTube has no ' + action + ' in its chat menu' };
    // (a pop-out that has just opened is still loading its chat)
    const item = await waitFor(() => [...document.querySelectorAll('yt-live-chat-text-message-renderer, yt-live-chat-paid-message-renderer')]
      .find((el) => el.id === messageId), 10000);
    if (!item) return { ok: false, why: "that message is no longer in YouTube's chat" };
    item.scrollIntoView({ block: 'center' });
    item.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
    await sleep(200);
    const opener = menuButton(item);
    if (!opener) return { ok: false, why: "YouTube's message menu did not appear" };
    opener.click();
    const choice = await waitFor(() => [...document.querySelectorAll('ytd-menu-service-item-renderer, tp-yt-paper-item, yt-list-item-view-model')]
      .find((el) => shown(el) && MENU[action].test(text(el))), 8000);
    if (!choice) {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      return { ok: false, why: 'YouTube did not offer that here (is this account the channel owner or a moderator?)' };
    }
    choice.click();
    if (action !== 'timeout') return { ok: true };       // Remove and Hide user are done on the click
    const asked = await waitFor(() => timeoutDialog([...document.querySelectorAll('tp-yt-paper-dialog')].filter(shown), seconds), 10000);
    if (!asked) return { ok: false, why: 'YouTube did not ask how long the timeout should be, so nobody was timed out' };
    if (asked.radio && asked.radio.getAttribute('aria-checked') !== 'true') {
      asked.radio.click();
      await sleep(200);
    }
    asked.yes.click();
    const closed = await waitFor(() => !shown(asked.dialog), 5000);
    return closed ? { ok: true } : { ok: false, why: "YouTube's timeout dialog stayed open" };
  }

  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (!['yt-say', 'yt-mod', 'yt-ready'].includes(message.type) || !message.video) return;
    if (new URLSearchParams(location.search).get('v') !== message.video) return;
    if (message.type === 'yt-say') {
      say(String(message.text || ''), !!message.dry).then(respond);
      return true;   // the answer comes later
    }
    if (embedded(location.search)) return;    // no moderation menu here: the chat pop-out answers instead
    if (message.type === 'yt-ready') {
      respond({ ok: !!document.querySelector('yt-live-chat-item-list-renderer') });
      return;
    }
    moderate(String(message.action || ''), String(message.message_id || ''), Number(message.seconds) || 0)
      .then(respond, () => respond({ ok: false, why: 'it failed' }));
    return true;
  });

  const here = new URLSearchParams(location.search);

  // Says so once YouTube's chat is on this page: the extension may be waiting to moderate in a pop-out it just opened.
  if (here.get('v') && !embedded(location.search)) {
    waitFor(() => document.querySelector('yt-live-chat-item-list-renderer'), 60000).then((list) => {
      if (list) ask('yt-chat-ready', { video: here.get('v') });
    });
  }

  // The chat pop-out CrossChat opened for moderating (crosschat=1) asks every half minute whether it is still needed;
  // the extension closes it once the live is over or CrossChat has closed.
  if (here.get('crosschat') === '1' && here.get('v') && !embedded(location.search)) {
    let misses = 0;
    const check = () => {
      try {
        chrome.runtime.sendMessage({ type: 'yt-check', video: here.get('v'), misses }, (answer) => {
          if (chrome.runtime.lastError || !answer) return;
          misses = answer.reached === false ? misses + 1 : 0;
        });
      } catch (e) { /* the extension was updated: this page is left as it is */ }
    };
    setInterval(check, 30000);
  }
})();
