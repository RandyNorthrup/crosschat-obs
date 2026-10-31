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

**The companion (paired devices on your home network)** runs on a second port, 4467 by default.

- It only starts listening once you pair a device or start a pairing, so nothing is exposed before you ask for it.
- Every request needs a paired device's key, except the pairing page itself.
  - The key is 32 random bytes in an HttpOnly, SameSite=Strict cookie.
  - CrossChat stores only its SHA-256 hash, in `devices.json`.
- Pairing codes are 6 random digits. They last 5 minutes, allow 5 wrong tries, and work once.
- Changes must come from the companion page itself, as JSON.
- Paired devices can read chat and reply, moderate, star, feature and send test events. They can't:
  - pair other devices;
  - connect Twitch;
  - change themes;
  - open windows;
  - go live on X;
  - act as the extension.
- It is plain `http` on your local network. Use it on a network you trust and don't forward the port; for remote use, a private network such as Tailscale is the safe way.

**Twitch's API:**

- CrossChat signs in with Twitch's device code flow as a public app. There is no client secret to leak.
- It asks for three permissions only: `user:write:chat`, `moderator:manage:chat_messages`, `moderator:manage:banned_users`.
- The tokens are encrypted for your Windows account with DPAPI (`twitch.bin`), so a copy of the file is useless elsewhere.
- **Disconnect** deletes the file and revokes the token at Twitch.

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
- `quick.json`, your quick replies;
- `devices.json`, hashes of paired devices' keys;
- `twitch.bin`, the Twitch token, encrypted for your Windows account;
- `crosschat.log`. The log has no passwords, keys, tokens or cookies.
