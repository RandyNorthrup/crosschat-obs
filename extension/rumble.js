// In the Rumble chat pop-out of the streamer's own live (CrossChat opens it once Rumble's official API says the live
// has started), this script types a reply from the CrossChat window into Rumble's chat box and sends it.
// Reading Rumble chat doesn't happen here: CrossChat gets it from Rumble's official Live Stream API. The script first
// asks CrossChat which chat is the streamer's, and does nothing in any other. It never presses the Rant button (Rants
// cost money) and never touches the Rumble login.
(() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const ask = (type, data) => new Promise((r) => {
    try { chrome.runtime.sendMessage({ type, data }, (a) => r(chrome.runtime.lastError ? null : a)); } catch (e) { r(null); }
  });
  const chatHere = () => (/^\/chat\/popup\/(\d+)/.exec(location.pathname) || [])[1] || '';

  async function say(text) {
    const answer = await ask('rm-check');
    if (!answer || !answer.chat || answer.chat !== chatHere()) return { ok: false, why: "this isn't your live's Rumble chat" };
    const box = document.getElementById('chat-message-text-input');
    if (!box) return { ok: false, why: 'sign in to Rumble in this browser to reply there' };
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(box, text);
    box.dispatchEvent(new Event('input', { bubbles: true }));
    await sleep(200);
    const send = document.querySelector('button.chat--send[name="send"]');      // (never the Rant button next to it)
    if (!send || send.disabled) return { ok: false, why: 'Rumble would not take the message' };
    send.click();
    for (let i = 0; i < 25; i++) {
      await sleep(200);
      if (!box.isConnected || box.value === '') return { ok: true };
    }
    return { ok: false, why: 'Rumble did not send it' };
  }

  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (message.type !== 'rm-say') return;
    say(String(message.text || '')).then(respond, () => respond({ ok: false, why: 'it failed' }));
    return true;   // the answer comes later
  });
})();
