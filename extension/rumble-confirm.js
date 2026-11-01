// Runs in the page of the streamer's Rumble chat pop-out itself (not in the extension's own copy of it), because only
// there can the browser's question box be answered. When rumble.js is about to press Rumble's own "Delete this
// message", it asks for this once: the next question within 3 seconds that is Rumble's "delete this message?" is
// answered yes, and every other question is left to the streamer as usual.
(() => {
  const ask = window.confirm;
  document.addEventListener('crosschat-rumble-confirm', () => {
    const until = Date.now() + 3000;
    window.confirm = function (message) {
      window.confirm = ask;
      if (Date.now() <= until && /delete this message/i.test(String(message))) return true;
      return ask.call(window, message);
    };
    setTimeout(() => { if (window.confirm !== ask) window.confirm = ask; }, 3000);
  });
})();
