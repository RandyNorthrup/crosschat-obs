# Security

## Reporting a problem

Please report security problems privately through GitHub: **[Report a vulnerability](https://github.com/RandyNorthrup/crosschat-obs/security/advisories/new)**. Don't open a public issue for them. You'll get an answer within a few days.

Fixes go into the newest release only.

## What leaves your PC

CrossChat has no server of its own. It makes no analytics or crash-report connections, and checks for updates only if you switch that on. Everything it sends goes straight from your PC to the services below, over HTTPS or TLS, and only for the features you turn on.

| Where | What is sent | When |
|---|---|---|
| Twitch chat (`irc.chat.twitch.tv`) | Nothing about you: chat is read signed out, as an anonymous viewer | A Twitch channel is set |
| Twitch (`gql.twitch.tv`, fallback `decapi.me`) | Your channel name, to get the viewer count | A Twitch channel is set and you're live |
| Twitch API (`id.twitch.tv`, `api.twitch.tv`) | Your Twitch token, your replies, your moderation actions | You pressed **Connect Twitch** |
| YouTube (`www.youtube.com`) | Your channel or video id, signed out, to read chat | A YouTube channel is set |
| Kick (`kick.com`, `web.kick.com`, Pusher) | Your channel name and its public channel number, signed out, to read chat; to `web.kick.com` also a random id made for that request, to get the address of Kick's chat feed | A Kick channel is set |
| Kick API (`id.kick.com`, `api.kick.com`) | Your Kick token, your replies, your moderation actions | You pressed **Connect Kick** |
| X, YouTube and TikTok, in your browser | The reply you typed, typed into the site's own chat box by the extension | You reply or moderate there |
| TikTok (`www.tiktok.com`), in your browser | Nothing beyond what your browser already does: CrossChat reads chat, gifts, follows, shares, likes (and joins, if you turn them on) from your own TikTok LIVE page there | A TikTok name is set and you're live |
| Facebook Live Producer, in your browser | Nothing beyond what your browser already does: CrossChat reads comments from Live Producer there | `"facebook": true` and you're live |
| Instagram's Live producer (`www.instagram.com`), in your browser | Nothing beyond what your browser already does: CrossChat reads comments from your own live there, and types your replies | `"instagram": true` and you're live |
| Rumble API (`rumble.com`) | Your own Live Stream API URL, to read your chat, Rants, subs and viewers | You connected Rumble and you're live |
| Discord (`discord.com`), through your webhook | Your webhook URL, and what you picked: a going-live notice with your channel links, the messages you show on stream, all chat. Only what viewers already see on stream | You connected Discord and you're live (and **Send a test post**) |
| GitHub (`api.github.com`) | Nothing about you: one request for the newest CrossChat version number. Like any web request, GitHub sees your IP address | You switched on **Tell me when a new version is out** (off by default), at most once a day |
| 7TV, BetterTTV, FrankerFaceZ | Your Twitch channel's public numeric id | Emotes are on (the default), once an hour |
| Google Fonts | A font request from your browser or OBS | Only if a theme uses a Google font |
| Microsoft or Google speech | The chat line being read aloud | Only if you pick a voice marked **online** for text-to-speech |

Viewers' names and messages are public chat. CrossChat keeps them only on your PC (see **Chat history** below).

## How CrossChat is built to be safe

**It runs only on your PC.**

- The hub listens on `127.0.0.1` and nowhere else.
- It answers only requests addressed to `127.0.0.1:<port>` or `localhost:<port>`, so a website can't reach it under another name (DNS rebinding).

**Other websites get nothing from it.**

- A page from another website can't read anything from the hub, not even the chat, and can't make it do anything: open a window, go live on X, feature a message, send test events, read chat history.
- The CrossChat window, the Theme Studio and the pairing page refuse to be put in another site's frame, where a hidden frame could take your clicks.
- Changes are accepted only as JSON from the hub's own pages. A page elsewhere can't send that without the browser checking first, and the hub refuses those checks.
- If a second CrossChat window takes over posting replies or reading aloud and then closes, the job goes back to the window that had it.
- Requests are limited: headers to 16 KB, bodies to 256 KB, theme files to 64 KB.
- Theme and history names are restricted to letters, digits and dashes, so a request can't reach other files.

**Your own overlay pages can't act as you.**

- Pages in your `custom_overlays` folder are served at `http://localhost:4466/custom/`. The browser keeps that address apart from the CrossChat window's `http://127.0.0.1:4466/`.
- They get their own files and the chat as viewers see it on stream: no filtered messages, notes, accounts, devices, filters, history or replies.
- They can't reply, moderate, change settings or open the CrossChat window, so an overlay pack downloaded from somewhere is safe to try.

**The widgets load nothing from elsewhere.** OBS's widgets only load CrossChat's own files, emote pictures from 7TV, BetterTTV, FrankerFaceZ and Twitch, and Google Fonts. A shared theme's custom CSS can't make them contact any other server. Custom CSS can still change what the widgets show, so only import themes from people you trust.

**The companion (paired devices on your home network)** runs on a second port, 4467 by default.

- It only starts listening once you pair a device or start a pairing, so nothing is exposed before you ask for it.
- It listens on your PC's home-network address only, not on every network adapter.
- **It refuses to start on a network Windows calls Public**, such as café or hotel Wi-Fi, where other people could listen in, or when Windows can't say. If your home network shows as Public, set it to Private: Settings > Network & internet > your network.
- If your PC moves to another network (a laptop taken out), or the network is switched to Public, the companion closes and starts again only on a Private network.
- **On a Mac** there is no such Private/Public setting for apps to ask, so the companion never starts by itself: it listens only on the address you put in `"remote": {"bind": ...}`.
- It closes when no device is paired and no pairing is in progress.
- Oversized or slow requests are dropped, and it takes at most 64 connections at once, so nobody on the network can tie it up.
- It answers only requests addressed to a plain IP address, so a website can't reach it under its own name (DNS rebinding).
- Every request needs a paired device's key, except the pairing page itself.
  - The key is 32 random bytes in an HttpOnly, SameSite=Strict cookie.
  - CrossChat stores only its SHA-256 hash, in `devices.json`.
- Pairing codes are 6 random digits. They last 5 minutes, allow 5 wrong tries, and work once.
- Changes must come from the companion page itself, as JSON.
- Paired devices can read chat and reply, moderate, star, feature, read a chat message aloud and send test events. They can't:
  - pair other devices;
  - connect Twitch, Kick, Rumble or Discord;
  - switch Tailscale or the update notice;
  - change themes, filters or text-to-speech settings;
  - read chat history;
  - open windows;
  - go live on X;
  - act as the extension;
  - make the PC say anything that isn't a message from the chat.
- It is plain `http` on your local network. Don't forward the port.
- **Away from home, with Tailscale** (off until you switch it on in Settings → Paired devices): the companion also listens on your PC's own Tailscale address, a private, encrypted network between your own devices.
  - The address counts only when Windows has it on Tailscale's own network adapter and that adapter is up. An address in Tailscale's range alone isn't trusted: internet providers hand out that range too.
  - Pairing is still needed. Anyone else on your tailnet (a shared node, say) reaches only the pairing page.
  - It closes when Tailscale stops or the switch goes off, and opens again when Tailscale is back.

**Twitch:**

- CrossChat signs in with Twitch's device code flow as a public app. There is no client secret to leak.
- It asks for three permissions only: `user:write:chat`, `moderator:manage:chat_messages`, `moderator:manage:banned_users`.
- The tokens are encrypted for your Windows account with DPAPI (`twitch.bin`), so a copy of the file is useless elsewhere. On a Mac, they're encrypted with AES-256 and sealed with HMAC-SHA256 under a random key CrossChat keeps in your login Keychain; the same goes for `kick.bin` and `rumble.bin`, and the uninstaller removes the key.
- **Disconnect** deletes the file and revokes the token at Twitch. If Twitch doesn't confirm, CrossChat says so, and you can remove it at twitch.tv → Settings → Connections.
- The sign-in page CrossChat opens is always on `https://www.twitch.tv/`.

**Rumble:**

- CrossChat reads Rumble through its official Live Stream API: a private URL you paste in Settings. It works like a password, so it's kept encrypted for your Windows account (`rumble.bin`), never logged, never put in an error message and never handed to a page or device.
- Rumble's answer also holds your stream key; CrossChat uses only the chat, Rants, subs and viewer count from it.
- **Disconnect** deletes the file. To cancel the URL itself, reset it at rumble.com/account/livestream-api.

**Discord:**

- CrossChat only posts, through a webhook you make in your server's settings. There is no bot, no Discord sign-in, and nothing is read from Discord. A webhook can post in its one channel and nothing else.
- The webhook URL works like a password, so it's kept encrypted for your Windows account (`discord.bin`), never logged, never put in an error message and never shown again or handed to a page or device. Connecting checks it with Discord first.
- Chat can't ping anyone: every post says no mentions are allowed, and every `@` is broken up. Discord formatting in chat is shown as typed, and links in chat are shown as code, which can't be clicked or previewed.
- Only what viewers already see on stream is posted: never messages your filters hid, notes, tests or anything about your PC. Nothing is posted during a test stream to this PC.
- Posts are spaced at least 2 seconds apart, and CrossChat waits as long as Discord asks. If the webhook is deleted, CrossChat stops and says so.
- **Disconnect** deletes the file. To stop the webhook everywhere, delete it in Discord.

**Update notice:** off unless you switch it on (in the installer or Settings → About). Then, at most once a day, CrossChat asks GitHub's public API for the newest release's version number: a fixed address, no cookies, nothing about you. It never downloads or installs anything. The link it shows is made by CrossChat from the version number and always goes to this repository's release page.

**Kick:**

- CrossChat signs in with Kick's OAuth 2.1 code flow with PKCE. Kick sends your browser back to `http://localhost:4466/kick/callback` on your own PC, and nowhere else.
- The sign-in is accepted only with the one-time random `state` CrossChat made when you pressed **Connect Kick**, so another site can't slip its own sign-in in.
- It asks for: `user:read`, `channel:read`, `chat:write`, `moderation:ban`, `moderation:chat_message:manage`.
- The tokens are encrypted for your Windows account with DPAPI (`kick.bin`). **Disconnect** deletes the file and revokes both tokens at Kick, and says so if Kick doesn't confirm.
- **About the Kick app secret.** Kick requires an app secret even for apps installed on people's PCs, so CrossChat's ships inside it, like every desktop app that signs in to Kick. It can't be used to get anyone's tokens: Kick only ever sends a sign-in back to the `localhost` address registered for the app, which is each person's own PC, and the PKCE code only works with the one-time key the hub made. If you'd rather use your own Kick app, register one at kick.com and set `"kick_client_id"` and `"kick_client_secret"` in `config.json`.

**The extension reads no logins.**

- It has no Chrome permissions at all: no cookies, no tabs, no storage.
- It may only touch these pages:
  - `127.0.0.1:4466`, the CrossChat window;
  - `studio.x.com`, for X Live;
  - `www.youtube.com/live_chat`, YouTube's chat box;
  - `www.tiktok.com`, for your own TikTok LIVE page. It first asks CrossChat which TikTok account is yours, and on every other TikTok page, someone else's LIVE included, it reads nothing and sends nothing;
  - `www.facebook.com/live/producer`, Facebook's Live Producer, which only ever shows your own broadcasts. No other part of Facebook;
  - `www.instagram.com/` (the home page only, where CrossChat opens it), for Instagram's Live producer, which opens over that page and only ever shows your own live. The extension reads only that live's comments and viewer count, and only while CrossChat says Instagram is on and you're live: never the feed, messages or profiles. It never presses the share button beside the comment box;
  - `rumble.com/chat/popup/`, Rumble's chat window, only to type your replies in your own live's chat (CrossChat tells it which one). It never presses the paid Rant button.
- TikTok has no public chat API. Tools that connect to TikTok LIVE chat directly usually go through an outside "signing" service, which learns which live you're reading (and gets your TikTok session too if you sign in through it to send messages). CrossChat uses no outside service: it reads chat only from your own LIVE page, in your own browser.
- On YouTube and X it types your reply into the site's own chat box, as the account already signed in there. YouTube moderation goes through YouTube's own message menu.
- Twitch and Kick replies don't use the extension at all: they go through those platforms' official APIs, from the hub.

**Chat text is never treated as code.**

- The pages put names and messages on screen as plain text, never as HTML.
- Emotes from 7TV, BetterTTV and FrankerFaceZ are kept only when the name is a plain word and the picture is on that service's own `https` address.
- Text-to-speech reads only messages from the chat. Filtered messages and your own messages are never read, and filtered messages can't be put on stream, from any device.

**Chat history:**

- Each stream's chat is saved on your PC, in `logs\` in your CrossChat folder, one file per stream, and deleted after 90 days. Set `"logs": {"enabled": false}` in `config.json` to keep none, or delete the folder at any time.
- History is only readable from the CrossChat window on your PC. Paired devices and websites can't read it.
- CSV exports neutralise spreadsheet formulas: a chat line starting with `=`, `+`, `-` or `@` is written as text, so opening the file in Excel can't run anything a viewer typed.
- HTML exports escape everything.

**OBS:** the hub reads OBS's WebSocket port and password from OBS's own settings file each time it connects. It never writes them anywhere and never logs them.

**Your files** are in `%LOCALAPPDATA%\CrossChat`:

- `config.json`, your channels;
- `themes\`;
- `quick.json`, your quick replies;
- `filters.json` and `tts.json`, your filter and text-to-speech settings;
- `devices.json`, hashes of paired devices' keys;
- `twitch.bin` and `kick.bin`, the tokens, `rumble.bin`, your Rumble API URL, and `discord.bin`, your Discord webhook, all encrypted for your Windows account;
- `update-check.json`, when the update notice last asked GitHub and what it found;
- `logs\`, chat history;
- `crosschat.log`. The log has no passwords, keys, tokens or cookies.

## Checking a download

Every release zip comes with a `.sha256` file and a signed build provenance attestation. The attestation proves the zip was built by this repository's release workflow from the tagged source. With the GitHub CLI:

```powershell
gh attestation verify CrossChat-1.4.0-windows.zip --repo RandyNorthrup/crosschat-obs
```

From 1.7.2 the Windows setup program also carries an Authenticode signature by **Randy Northrup** (Azure Artifact Signing), timestamped. To check it: right-click the file → Properties → Digital Signatures, or in PowerShell `Get-AuthenticodeSignature .\CrossChat-Setup-1.7.2.exe` (Status should be `Valid`, the signer `CN=Randy Northrup, …`).

How releases are made:

- The release is built from a fresh checkout by a job that installs nothing. Tests run in a separate job with read-only access.
- GitHub Actions are pinned to exact commits.
- Code signing runs in the release job from a GitHub environment only `v*` tags can use. No signing secret is stored: Azure trusts GitHub's short-lived OIDC token from that environment only, and the identity it gets can only sign with CrossChat's certificate profile. The job checks the signature, signer and timestamp before publishing.
- The installer installs CrossChat's two Python packages and their dependencies at the exact versions it was tested with, checked against their SHA-256 hashes (`hub/requirements.lock`). pip refuses anything that doesn't match.
