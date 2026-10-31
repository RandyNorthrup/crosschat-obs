// Fills in X's "Create Livestream" form and presses Go Live. (x-chat.js takes over once the livestream runs.)
//
// It runs on https://studio.x.com/live only when the address ends in one of these, and only if the CrossChat
// hub on this PC (hub/hub.py) confirms it asked for exactly that a moment ago:
//   #golive          public livestream
//   #golive-private  visible to the account owner only (for testing)
//   #golive-dry      fill the form, never press Go Live
//
// X only reads whether the encoder is connected when the page loads. So while the source still says
// "Not connected", the script reloads the page and looks again, for up to three minutes.
(async () => {
  const MODES = { '#golive': 'live', '#golive-private': 'private', '#golive-dry': 'dry' };
  const JOB = 'crosschat-job';
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const ask = (type, data) => new Promise((r) => chrome.runtime.sendMessage({ type, data }, (a) => r(chrome.runtime.lastError ? { reached: false } : a)));
  const text = (el) => (el.textContent || '').replace(/\s+/g, ' ').trim();

  const bar = document.createElement('div');
  bar.style.cssText = 'position:fixed;left:0;right:0;top:0;z-index:2147483647;padding:10px 16px;font:600 14px system-ui,sans-serif;' +
    'color:#fff;background:#24384a;border-bottom:2px solid #b87045;text-align:center;pointer-events:none';
  const say = (message, colour) => { bar.textContent = 'CrossChat: ' + message; if (colour) bar.style.background = colour; document.body.appendChild(bar); };

  // A job is either new (the address carries the request and the hub confirms it) or carried over a reload.
  let job = null;
  try { job = JSON.parse(sessionStorage.getItem(JOB) || 'null'); } catch (e) { job = null; }
  if (job && Date.now() > job.until) job = null;
  const asked = MODES[location.hash];
  if (asked) {
    history.replaceState(null, '', location.pathname + location.search);   // the request is used once
    const state = await ask('state');
    if (!state || !state.reached) { say('the CrossChat hub on this PC is not running (it starts with OBS). Nothing was done.', '#7a1d14'); return; }
    if (state.data.go !== asked) { say('nobody asked for a livestream just now, so nothing was done.'); await sleep(6000); bar.remove(); return; }
    job = { mode: asked, want: state.data, until: Date.now() + 180000 };
  }
  sessionStorage.removeItem(JOB);
  if (!job) return;
  const { mode, want } = job;

  let step = 'start';
  const waitFor = async (find, seconds, what) => {
    step = what;
    for (let i = 0; i < seconds * 4; i++) {
      const found = find();
      if (found) return found;
      await sleep(250);
    }
    throw new Error(what);
  };
  const shown = (el) => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const button = (label, root) => [...(root || document).querySelectorAll('button')].find((b) =>
    shown(b) === label || text(b) === label || b.getAttribute('aria-label') === label);
  const usable = (b) => b && !b.disabled && b.getAttribute('aria-disabled') !== 'true';
  const dialog = () => [...document.querySelectorAll('[role="dialog"]')].find((d) => text(d).includes('Create Livestream'));
  const checked = (radio) => radio.checked === true || radio.getAttribute('aria-checked') === 'true' ||
    radio.hasAttribute('data-checked') || radio.dataset.state === 'checked';
  const titleBox = () => {
    const label = [...dialog().querySelectorAll('label')].find((l) => text(l) === 'Title');
    return (label && label.htmlFor && document.getElementById(label.htmlFor)) || dialog().querySelector('input[type="text"], input:not([type])');
  };

  async function openTab(name) {
    const tab = await waitFor(() => [...dialog().querySelectorAll('[role="tab"]')].find((t) => text(t) === name), 10, 'the ' + name + ' tab');
    tab.click();
    await sleep(500);
  }

  // Pick one option of a group of round buttons by its label, then make sure it really is the chosen one.
  async function choose(group, label) {
    const find = () => {
      const box = [...dialog().querySelectorAll('[role="radiogroup"]')].find((g) => {
        const named = g.getAttribute('aria-label') || text(document.getElementById(g.getAttribute('aria-labelledby')) || document.createElement('i'));
        return named === group;
      });
      if (!box) return null;
      const radios = [...box.querySelectorAll('[role="radio"], input[type="radio"]')];
      return radios.find((r) => {
        const row = r.closest('label') || r.parentElement;
        return (r.getAttribute('aria-label') || '') === label || text(row).startsWith(label);
      });
    };
    const radio = await waitFor(find, 10, group + ' = ' + label);
    for (const target of [radio, radio.closest('label'), radio.parentElement]) {
      if (checked(find())) return;
      if (target) { target.click(); await sleep(400); }
    }
    if (!checked(find())) throw new Error(group + ' would not switch to ' + label);
  }

  try {
    say(mode === 'dry' ? 'filling in the form as a test…' : 'starting the X livestream…');
    await waitFor(() => usable(button('New Livestream')), 30, 'the New Livestream button');
    button('New Livestream').click();
    await waitFor(dialog, 15, 'the Create Livestream form');
    await sleep(700);

    step = 'the source';
    const source = await waitFor(() => dialog().querySelector('[role="combobox"]'), 10, 'the source');
    if (!text(source).includes(want.source)) throw new Error('the source is not "' + want.source + '"');
    const connected = !!source.querySelector('img[alt="Connected"], [aria-label="Connected"]');
    if (!connected && mode !== 'dry') {
      step = 'video from OBS reaching X';
      if (Date.now() + 8000 > job.until) throw new Error(step);
      say('waiting for X to see the video from OBS…');
      sessionStorage.setItem(JOB, JSON.stringify(job));      // look again after a reload
      await sleep(5000);
      location.reload();
      return;
    }

    step = 'Now';
    const now = button('Now', dialog());
    if (now) { now.click(); await sleep(300); }

    await openTab('Details');
    const title = await waitFor(titleBox, 10, 'the Title box');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(title, want.title);
    title.dispatchEvent(new Event('input', { bubbles: true }));
    title.dispatchEvent(new Event('change', { bubbles: true }));
    await sleep(400);

    await openTab('Audience');
    await choose('Visibility', mode === 'live' ? 'Public' : 'Private');

    if (want.post && mode === 'live') {
      await openTab('Post');
      const box = await waitFor(() => dialog().querySelector('[contenteditable="true"], textarea'), 10, 'the post box');
      box.focus();
      document.execCommand('insertText', false, want.post);
      await sleep(400);
    }

    await openTab('Details');                                 // the form must still hold the title after the other tabs
    step = 'the title';
    if (titleBox().value !== want.title) throw new Error('the title did not stick');

    if (mode === 'dry') {
      say('test finished: the form is filled in and Go Live was NOT pressed. Close the form when you have looked.', '#2f5d3a');
      await ask('result', { ok: 1, mode, step: 'filled' });
      return;
    }

    // X lets Go Live be pressed only some time after the source turns "Connected" (it can take a minute).
    say('form filled in; waiting for X to allow Go Live…');
    const go = await waitFor(() => (usable(button('Go Live')) ? button('Go Live') : null), 180, 'X allowing Go Live');
    step = 'Go Live';
    go.click();
    await waitFor(() => !dialog(), 60, 'X confirming the livestream');
    say(mode === 'private' ? 'private test livestream started.' : 'you are live on X.', '#2f5d3a');
    await ask('result', { ok: 1, mode, step: 'live' });
    // Show the new livestream's own page: it has the viewer count and the chat, which x-chat.js passes on.
    const past = (a) => {                                     // earlier livestreams sit under a "Past" heading
      const group = a.closest('tbody, [role="rowgroup"]');
      const heading = group && group.querySelector('h1, h2, h3, h4, [role="heading"]');
      return !!heading && /^past/i.test(text(heading));
    };
    for (let i = 0; i < 80 && !/^\/live\/\w/.test(location.pathname); i++) {
      const link = [...document.querySelectorAll('a[href*="/live/"]')].find((a) => text(a) === want.title && !past(a));
      if (link) { link.click(); await sleep(3000); }
      await sleep(250);
    }
    await sleep(5000);
    bar.remove();
  } catch (error) {
    say('stopped at: ' + step + '. Nothing was posted unless you see it below. You can finish by hand.', '#7a1d14');
    await ask('result', { ok: 0, mode, step });
  }
})();
