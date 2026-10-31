// Platform glyphs for the overlays and the Theme Studio.
// Twitch, YouTube, Kick and X paths are from Simple Icons 16.33.0 (CC0 1.0, https://simpleicons.org),
// copied from https://unpkg.com/simple-icons@16.33.0/icons/<name>.svg. The brands themselves belong to their owners.
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.CrossChatIcons = api;
})(typeof self !== 'undefined' ? self : globalThis, function () {
  const PATHS = {
    twitch: 'M11.571 4.714h1.715v5.143H11.57zm4.715 0H18v5.143h-1.714zM6 0L1.714 4.286v15.428h5.143V24l4.286-4.286h3.428L22.286 12V0zm14.571 11.143l-3.428 3.428h-3.429l-3 3v-3H6.857V1.714h13.714Z',
    youtube: 'M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z',
    kick: 'M1.333 0h8v5.333H12V2.667h2.667V0h8v8H20v2.667h-2.667v2.666H20V16h2.667v8h-8v-2.667H12v-2.666H9.333V24h-8Z',
    x: 'M14.234 10.162 22.977 0h-2.072l-7.591 8.824L7.251 0H.258l9.168 13.343L.258 24H2.33l8.016-9.318L16.749 24h6.993zm-2.837 3.299-.929-1.329L3.076 1.56h3.182l5.965 8.532.929 1.329 7.754 11.09h-3.182z',
    // a plain speech bubble for anything else (drawn for CrossChat, same licence as the project)
    chat: 'M4 2h16a3 3 0 0 1 3 3v10a3 3 0 0 1-3 3h-7.6L7 22.5V18H4a3 3 0 0 1-3-3V5a3 3 0 0 1 3-3Z',
  };
  const NAMES = { twitch: 'Twitch', youtube: 'YouTube', kick: 'Kick', x: 'X' };

  // An <svg> for `platform`, filled with currentColor so CSS decides its colour.
  function icon(platform, doc) {
    doc = doc || document;
    const ns = 'http://www.w3.org/2000/svg';
    const svg = doc.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    const path = doc.createElementNS(ns, 'path');
    path.setAttribute('d', PATHS[platform] || PATHS.chat);
    path.setAttribute('fill', 'currentColor');
    svg.appendChild(path);
    return svg;
  }

  return { PATHS, NAMES, icon };
});
