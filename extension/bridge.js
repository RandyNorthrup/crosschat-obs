// Runs inside the CrossChat window (the page served by the hub, hub/hub.py). Hands a reply typed there to the
// extension, which posts it, and passes the outcome back to the page.
document.documentElement.dataset.crosschat = chrome.runtime.getManifest().version;

window.addEventListener('message', (event) => {
  const data = event.data;
  if (event.source !== window || event.origin !== location.origin || !data || data.crosschat !== 'send') return;
  const back = (answer) => window.postMessage({ crosschat: 'sent', n: data.n, answer }, location.origin);
  try {
    chrome.runtime.sendMessage({ type: 'send', data: { to: data.to, text: data.text, reply: data.reply, dry: !!data.dry } },
      (answer) => back(chrome.runtime.lastError ? null : answer));
  } catch (e) {
    back(null);   // the extension was updated after this window opened: the window has to be opened again
  }
});
