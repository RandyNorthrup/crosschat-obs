// Which link of a Live Producer comment names its writer, and what is left of its words. facebook.js reads the page.
globalThis.CrossChatFacebookComments = (() => {
  const { clean } = globalThis.CrossChatCommon;

  // The link with the commenter's name. Facebook marks each comment as an article whose links carry the comment's own
  // id; a viewer's comment starts with their picture, a link too (hidden from screen readers, no text), so the first
  // link with text is the name.
  const nameLink = (article) => [...article.querySelectorAll('a[href*="comment_id="]')].find((a) => clean(a.textContent)) || null;

  // The words of a comment, from the text around the links: without the "·" Facebook puts between the name and the
  // comment, and without its own "Posting…" under a fresh comment.
  const words = (raw) => clean(raw).replace(/^[·•]\s*/, '').replace(/\s*Posting(…|\.\.\.)$/i, '');

  return { nameLink, words };
})();
