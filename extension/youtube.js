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

  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (message.type !== 'yt-say' || !message.video) return;
    if (new URLSearchParams(location.search).get('v') !== message.video) return;
    say(String(message.text || ''), !!message.dry).then(respond);
    return true;   // the answer comes later
  });
})();
