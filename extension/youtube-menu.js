// How CrossChat tells apart the buttons, menu entries and dialogs of YouTube's live chat. youtube.js does the clicking.
globalThis.CrossChatYouTubeMenu = (() => {
  const text = (el) => (el.innerText || el.textContent || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
  const MENU = { delete: /^(remove|delete)$/i, timeout: /^put user in timeout$/i, ban: /^hide user on this channel$/i };
  const CONFIRM = /^confirm$/i;
  // "Put user in timeout" asks how long (10 seconds up to 24 hours, 5 minutes picked); Remove and Hide user act at once.
  const TIMEOUTS = [[10, /^10 seconds$/i], [60, /^1 minute$/i], [300, /^5 minutes$/i], [600, /^10 minutes$/i],
    [1800, /^30 minutes$/i], [86400, /^24 hours$/i]];
  const embedded = (search) => new URLSearchParams(search).has('embed_domain');

  // The timeout length YouTube offers that is nearest the one asked for (5 minutes when none is given).
  function timeoutChoice(seconds) {
    const want = Number(seconds) > 0 ? Number(seconds) : 300;
    return TIMEOUTS.reduce((best, t) => (Math.abs(Math.log(t[0] / want)) < Math.abs(Math.log(best[0] / want)) ? t : best));
  }

  // The message's own "Chat actions" menu button. A row can hold other buttons before it (YouTube shows a top fan's
  // "#1" rank there), and one selector list returns whichever match comes first in the row, so each is asked in turn
  // and no other button is ever clicked.
  const MENU_BUTTONS = ['#menu-button button', '#menu button', 'button[aria-label="Chat actions"]'];
  function menuButton(item) {
    for (const selector of MENU_BUTTONS) {
      const found = item.querySelector(selector);
      if (found) return found;
    }
    return null;
  }

  // Whether YouTube has it open now. Its menus and dialogs stay in the page once closed (and still hold the last
  // message's entries), so only an open one is ever clicked. YouTube marks a closed one aria-hidden="true" the moment
  // it closes; the drawing comes later, and a background tab (where the chat pop-out sits) doesn't draw it at all until
  // someone looks, so whether it is on screen can't tell.
  const shown = (el) => !!el && !el.closest('[aria-hidden="true"]');

  // The open "Timeout duration" dialog, its radio for that length and its Confirm button.
  function timeoutDialog(dialogs, seconds) {
    for (const d of dialogs) {
      const radios = [...d.querySelectorAll('[role="radio"]')];
      const yes = [...d.querySelectorAll('button')].find((b) => CONFIRM.test(text(b)));
      if (radios.length && yes) {
        const label = timeoutChoice(seconds)[1];
        return { dialog: d, radio: radios.find((r) => label.test(r.getAttribute('aria-label') || text(r))) || null, yes };
      }
    }
    return null;
  }

  return { text, menuButton, MENU, CONFIRM, TIMEOUTS, timeoutChoice, timeoutDialog, embedded, shown };
})();
