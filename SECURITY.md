# Security

## Reporting a problem

Please report security problems privately through GitHub: **[Report a vulnerability](https://github.com/RandyNorthrup/crosschat-obs/security/advisories/new)**. Don't open a public issue for them. You'll get an answer within a few days.

Fixes go into the newest release only.

## How CrossChat is built to be safe

**It runs only on your PC.**

- The hub listens on `127.0.0.1` and nowhere else.
- It answers only requests addressed to `127.0.0.1:<port>` or `localhost:<port>`, so a website can't reach it under another name (DNS rebinding).

**Other websites can't make it do anything.**

- Reading the public chat feed, the widgets and the theme list is allowed from anywhere on your PC. That's how OBS shows the widgets.
- Anything that acts (opening a window, going live on X, featuring a message, sending test events) is refused when another website asks for it.
- Changes (saving, deleting or picking a theme, test events) are accepted only as JSON from the hub's own pages. A page elsewhere can't send that without the browser checking first, and the hub refuses those checks.
- Bodies are limited to 256 KB and theme files to 64 KB.
- Theme names are restricted to lowercase letters, digits and dashes, so a request can't reach other files.

**Chat text is never treated as code.** The pages put names and messages on screen as plain text, never as HTML.

**Your accounts:**

- Chat is read through each platform's public, signed-out feed.
- Replies are posted from your own browser by the CrossChat extension, with the accounts already signed in there.
- For Twitch, the extension reads the browser's Twitch login cookie to post your reply over Twitch's own chat connection. It's read for that connection only, is never stored, and goes nowhere else.
- On YouTube and X, the extension types into those sites' own chat boxes.

**The extension's permissions:**

- `cookies`, for the Twitch login described above.
- Pages it may touch:
  - `127.0.0.1:4466`, the CrossChat window;
  - `studio.x.com`, for X Live;
  - `www.twitch.tv`, for that cookie;
  - `www.youtube.com/live_chat`, YouTube's chat box.

**OBS:** the hub reads OBS's WebSocket port and password from OBS's own settings file each time it connects. It never writes them anywhere and never logs them.

**No telemetry.** CrossChat makes no analytics, crash-report or update-check connections. The only connections it makes are to the chat platforms you configured and, if a theme names one, Google Fonts.

**Your files** are in `%LOCALAPPDATA%\CrossChat`:

- `config.json`, your channels;
- `themes\`;
- `crosschat.log`. The log has no passwords, keys or cookies.
