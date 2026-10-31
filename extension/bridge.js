// Runs inside the CrossChat window (the page served by the hub, hub/hub.py). Hands a reply or a moderation job
// from that page to the extension, which carries it out, and passes the outcome back to the page.
document.documentElement.dataset.crosschat = chrome.runtime.getManifest().version;

const JOBS = { send: ['send', 'sent'], mod: ['mod', 'modded'] };       // page asks -> extension type, page answer

window.addEventListener('message', (event) => {
  const data = event.data;
  if (event.source !== window || event.origin !== location.origin || !data || !JOBS[data.crosschat]) return;
  const [type, answerType] = JOBS[data.crosschat];
  const back = (answer) => window.postMessage({ crosschat: answerType, n: data.n, answer }, location.origin);
  const job = type === 'send'
    ? { to: data.to, text: data.text, reply: data.reply, dry: !!data.dry }
    : { p: data.p, action: data.action, message_id: data.message_id, user_id: data.user_id, name: data.name };
  try {
    chrome.runtime.sendMessage({ type, data: job }, (answer) => back(chrome.runtime.lastError ? null : answer));
  } catch (e) {
    back(null);   // the extension was updated after this window opened: the window has to be opened again
  }
});
