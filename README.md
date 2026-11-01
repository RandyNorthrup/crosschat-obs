<p align="center">
  <img src="assets/brand/banner.png" alt="CrossChat: every stream chat in one window. Reply everywhere. Theme it on stream." width="100%">
</p>

<p align="center">
  <a href="https://github.com/RandyNorthrup/crosschat-obs/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/RandyNorthrup/crosschat-obs?label=release&color=e3a57b"></a>
  <a href="https://github.com/RandyNorthrup/crosschat-obs/releases"><img alt="Downloads" src="https://img.shields.io/github/downloads/RandyNorthrup/crosschat-obs/total?label=downloads&color=2b9c9a"></a>
  <a href="https://github.com/RandyNorthrup/crosschat-obs/actions/workflows/ci.yml"><img alt="Checks" src="https://img.shields.io/github/actions/workflow/status/RandyNorthrup/crosschat-obs/ci.yml?branch=main&label=checks"></a>
  <img alt="Windows 10 and 11" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4">
  <img alt="macOS beta" src="https://img.shields.io/badge/macOS-beta-999999">
  <img alt="Tested with OBS Studio 33.0.1" src="https://img.shields.io/badge/OBS%20Studio-33.0.1-302E31">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-b87045"></a>
  <a href="https://github.com/sponsors/RandyNorthrup"><img alt="Sponsor on GitHub" src="https://img.shields.io/badge/sponsor-GitHub-db61a2"></a>
  <a href="https://www.paypal.com/donate/?hosted_button_id=Q9VC7B42R7K82"><img alt="Donate with PayPal" src="https://img.shields.io/badge/donate-PayPal-0070ba"></a>
</p>

**CrossChat** is a free companion for OBS Studio when you stream to several platforms at once. It reads **Twitch, YouTube, Kick, X, TikTok, Facebook, Instagram and Rumble** chat into one window, lets you **answer everyone with one message** (or one person on their own platform), **moderates** Twitch, YouTube, Kick and Rumble (and deletes Facebook comments), puts **themeable chat, featured messages, viewer counts and alerts** on your stream, and **starts and ends your X livestream together with OBS**. Pair your **phone or another PC** to read, answer and moderate chat from there. Everything runs on your own PC and home network.

<p align="center">
  <img src="assets/video/overview.webp" alt="CrossChat in action: a question from YouTube is put on stream, then one reply goes out to Twitch, YouTube and X at once" width="100%"><br>
  <sub>Left: what viewers see. Right: your CrossChat window. Made-up chat from the built-in demo. <a href="assets/video/overview.mp4"><b>▶ Watch the full 48-second tour (MP4)</b></a></sub>
</p>

## Features

**One chat window for every platform**
- Twitch, YouTube, Kick, X, TikTok LIVE, Facebook Live, Instagram Live and Rumble chat in one list, each line tagged with where it came from.
- Viewer counts per platform and in total.
- Subs, raids, cheers, Super Chats, memberships, Rumble Rants and TikTok gifts, follows and shares are marked in the list.
- **Viewer cards:** click a name to see their messages this stream and in earlier streams, and act on them.
- Deleted messages and timed-out viewers are struck through.
- **7TV, BetterTTV and FrankerFaceZ emotes**, as well as each platform's own.
- **First-time chatters** stand out, and each platform's connection health is a glance away.
- **Filters** hide words, viewers, chat commands and bots from your stream without deleting anything.
- **Read chat aloud**: questions, everything, alerts or a `!tts` command, with Windows' own voices.
- **Chat history**: every stream kept on your PC for 90 days, to search and export as CSV or HTML.
- Light, dark, or follows Windows.
- Opens by itself when OBS starts streaming, and closes two minutes after you stop.

**Reply and moderate from one place**
- Type once to post to every live platform, as you.
- Use **only:** to post to a single platform, or open a message and press **reply** to answer that person on their own platform. On Twitch that's a threaded reply.
- **Quick replies:** one-tap lines and emoji you edit yourself.
- **Moderation:** delete a message, time out or ban, on Twitch, YouTube and Kick; delete or mute on Rumble; delete comments on Facebook.
- **Answer later:** star messages to come back to. Questions are picked out for you.
- **Twitch and Kick through their official APIs.** Connect once in Settings.
- YouTube and X go out through your signed-in browser and the CrossChat extension.
- Test mode (`?dry`) walks through the whole path without posting anything.

**Companion on your phone or another PC**
- Pair with a QR code (phone) or a link and a 6-digit code (another PC's browser). The full chat app then runs on any phone, tablet or PC on your home network, with no install and no logins on that device. A second PC can give it its own app window.
- Read, reply, use quick replies, moderate, star, put messages on stream, and send test alerts.
- Only paired devices get in, and you can remove one at any time. See **[docs/COMPANION.md](docs/COMPANION.md)**.
- **Away from home too**, with [Tailscale](#the-companion-away-from-home-tailscale): one switch in Settings, pairing still required.

**Discord**
- Post to a channel of your Discord server while you're live: a going-live notice with your channel links, the messages you show on stream, or all chat. You pick.
- Through a webhook you make in Discord: no bot, no sign-in. Chat can't ping anyone there, and hidden messages never go.

**Four on-stream widgets** (OBS Browser Sources)
- **Chat feed**: the merged chat, or only the platforms you choose.
- **Featured message**: hover any message in the CrossChat window, press **show**, and it appears big on stream.
- **Viewer counter**: everyone watching, in total and per platform.
- **Alerts**: subs, resubs, gifts, raids, cheers, memberships and Super Chats, with an optional chime.

**Theme Studio**
- Eight built-in looks, and full control over fonts, colours, layout, animation, platform icons and custom CSS.
- Live preview over your own screenshot, and one-click test events to the sources already in OBS.
- A different theme per scene.

**X Live started with OBS**
- X only goes live when you press Go Live on its Live Studio page. The CrossChat browser extension does that for you when OBS starts streaming, and ends the livestream when you stop.
- X's chat and viewer count join the CrossChat window.

**Follows OBS, stays local**
- The OBS script starts CrossChat with OBS and stops it when OBS closes.
- CrossChat reads its OBS WebSocket settings from OBS itself, and portable OBS works too.
- No account, server or telemetry. Update checks only if you switch them on: then CrossChat asks GitHub once a day and shows a link to the new release (it never downloads anything itself).

## See it in action

| | |
|---|---|
| **The tour** (48 s): a question put on stream, one reply to every platform, a message deleted, Answer later and Questions, an alert on stream. | [▶ overview.mp4](assets/video/overview.mp4) |
| **Phone companion** (29 s, vertical): a question tapped onto the stream, a quick reply, a timeout, the Questions view. | [▶ companion-vertical.mp4](assets/video/companion-vertical.mp4) |
| **Theme Studio** (35 s): six of the built-in looks in a row, then the accent colour, the text size and the layout changed live. | [▶ theme-studio.mp4](assets/video/theme-studio.mp4) |
| **Recorded in OBS 33.0.1** (25 s): the four widgets running in a real OBS scene. | [▶ obs-recording.mp4](assets/video/obs-recording.mp4) |

<p align="center"><img src="assets/video/theme-studio.webp" alt="The Theme Studio cycling through the built-in themes on a stream-sized preview" width="100%"></p>

## Screenshots

**The CrossChat window**

| Live chat | Reply to one person, message on stream | Moderate |
|:-:|:-:|:-:|
| <img src="assets/screenshots/chat-dark.png" alt="The CrossChat window: viewers per platform and chat from Twitch, YouTube, Kick and X" width="260"> | <img src="assets/screenshots/chat-reply.png" alt="Replying to a YouTube viewer while their question is featured on stream" width="260"> | <img src="assets/screenshots/chat-mod.png" alt="A message's actions: reply, show on stream, answer later, delete, timeouts, ban, quick replies" width="260"> |
| **Questions** | **Quick replies** | **Settings** |
| <img src="assets/screenshots/chat-questions.png" alt="The Questions view: only messages that look like questions" width="260"> | <img src="assets/screenshots/chat-quick.png" alt="Editing quick replies" width="260"> | <img src="assets/screenshots/chat-settings.png" alt="Settings: light or dark, Twitch connected, pair a device, test events" width="260"> |

| Read chat aloud | Filters | Chat history | Connection health |
|:-:|:-:|:-:|:-:|
| <img src="assets/screenshots/chat-tts.png" alt="Text-to-speech settings: what to read, voice, speed and volume" width="195"> | <img src="assets/screenshots/chat-filters.png" alt="Filters: hidden words, viewers, commands and bots, with hidden messages dimmed in the chat" width="195"> | <img src="assets/screenshots/chat-history.png" alt="A past stream's chat: search, platform filter, questions, CSV and HTML export" width="195"> | <img src="assets/screenshots/chat-health.png" alt="Connections: how long each platform has been connected, last message and reconnects, and Twitch and Kick sign-in" width="195"> |

**The companion on a phone or another PC**

| On a phone | Pairing | On another PC |
|:-:|:-:|:-:|
| <img src="assets/screenshots/companion-phone.png" alt="The CrossChat companion on a phone" width="200"> | <img src="assets/screenshots/companion-pair.png" alt="Pairing a device: QR code, 6-digit code and paired devices" width="230"> | <img src="assets/screenshots/companion-desktop.png" alt="The CrossChat companion in a browser window on a second PC" width="380"> |

**On stream**

| Alerts | |
|:-:|:-:|
| <img src="assets/screenshots/alert-sub.png" alt="Alert: a Twitch subscription" width="400"> | <img src="assets/screenshots/alert-raid.png" alt="Alert: a Twitch raid with 37 viewers" width="400"> |
| <img src="assets/screenshots/alert-superchat.png" alt="Alert: a YouTube Super Chat" width="400"> | <img src="assets/screenshots/alert-cheer.png" alt="Alert: a Twitch cheer of 500 bits" width="400"> |
| **Featured message** | **Viewer counter** |
| <img src="assets/screenshots/featured.png" alt="A viewer's question shown big on stream" width="400"> | <img src="assets/screenshots/viewers.png" alt="Everyone watching, in total and per platform" width="400"> |

**Theme Studio:** change any part of the look and watch all four widgets update over a stream-sized preview.

<img src="assets/screenshots/studio.png" alt="The Theme Studio: theme list, settings and a live preview of all four widgets">

**Inside OBS 33.0.1:** the four widgets added as Browser Sources.

<img src="assets/screenshots/obs-window.png" alt="OBS Studio 33.0.1 with the CrossChat chat, featured, viewers and alerts sources in a scene">

### Built-in themes

| Classic | Minimal outline | Glass | Bubbles |
|:-:|:-:|:-:|:-:|
| <img src="assets/themes/classic.png" width="200" alt="Classic theme"> | <img src="assets/themes/minimal.png" width="200" alt="Minimal outline theme"> | <img src="assets/themes/glass.png" width="200" alt="Glass theme"> | <img src="assets/themes/bubbles.png" width="200" alt="Bubbles theme"> |
| **Compact** | **Neon** | **Paper** | **High contrast** |
| <img src="assets/themes/compact.png" width="200" alt="Compact theme"> | <img src="assets/themes/neon.png" width="200" alt="Neon theme"> | <img src="assets/themes/paper.png" width="200" alt="Paper theme"> | <img src="assets/themes/contrast.png" width="200" alt="High contrast theme"> |

Every setting, the CSS hooks and how to share themes are in **[docs/THEMES.md](docs/THEMES.md)**.

## What you need

| | |
|---|---|
| **PC** | Windows 10 or 11, 64-bit (tested on Windows 11). A Mac works too, as a beta: see [Mac (beta)](#mac-beta). |
| **OBS Studio** | 28 or newer, with its built-in WebSocket server. Tested with **33.0.1** (obs-websocket 5.7.6). |
| **Browser** | Google Chrome, or Microsoft Edge. Needed only for replying, and for X and TikTok. |
| **Python** | Nothing to install: the setup program brings its own (python.org's embeddable Python). The zip's `Install.cmd` needs Python 3.10 or newer, and offers to install it. |
| **X Live** *(optional)* | X Premium with access to [X Live Studio](https://studio.x.com/live), and OBS sending video to X (see [X Live](#x-live)). |
| **TikTok LIVE** *(optional)* | Signed in to TikTok in the same browser, and OBS sending video to TikTok (see [TikTok LIVE](#tiktok-live)). |
| **Facebook Live, Rumble** *(optional)* | Signed in to them in the same browser (see [Facebook Live and Rumble](#facebook-live-and-rumble)). |
| **Instagram Live** *(optional)* | Signed in to Instagram in the same browser, and OBS sending video to Instagram (see [Instagram Live](#instagram-live)). |

CrossChat doesn't send your video anywhere. OBS does that. To stream to several platforms at once, use what you already use for that: an OBS multi-output plugin such as [obs-multi-rtmp](https://github.com/sorayuki/obs-multi-rtmp), or a restreaming service.

## Install

1. **Download** `CrossChat-Setup-<version>.exe` from **[Releases](https://github.com/RandyNorthrup/crosschat-obs/releases/latest)** and run it. It does the following:
   - installs CrossChat for your Windows account in `%LOCALAPPDATA%\CrossChat`, with its own Python, and needs no administrator rights;
   - turns on OBS's WebSocket server if it's off (it asks first);
   - adds a **CrossChat** folder to the Start menu, and CrossChat to *Settings → Apps*.

   Running a newer one later updates CrossChat and keeps your settings, themes, sign-ins and chat history. After an update, open `chrome://extensions` (or `edge://extensions`) and press the reload arrow on CrossChat: the browser keeps running the old extension until you do, and the chat window says so. From 1.7.2 the setup program is code-signed by **Randy Northrup** (Azure Artifact Signing). A newly signed program can still get a "Windows protected your PC" notice until Windows has seen enough downloads of it: choose **More info**, check the publisher says Randy Northrup, then **Run anyway**. Details, silent install and how it's built: [docs/INSTALLER.md](docs/INSTALLER.md).
2. **Set your channels:** Start menu → CrossChat → **Open chat** → **Settings**.
3. **Add the script to OBS:** *Tools → Scripts → +*, then pick `%LOCALAPPDATA%\CrossChat\obs\crosschat.lua`. Setup puts this path on your clipboard.
4. **Add the extension** to Chrome or Edge:
   1. Open `chrome://extensions` (or `edge://extensions`).
   2. Switch on **Developer mode**.
   3. Press **Load unpacked** and pick `%LOCALAPPDATA%\CrossChat\extension`.

   Reading chat and the on-stream widgets work without the extension. Replying and X Live need it.
5. **Add the widgets you want** to your scenes as Browser Sources:

   | Widget | URL | Size |
   |---|---|---|
   | Chat feed | `http://127.0.0.1:4466/overlay/chat` | 450 × 800 |
   | Featured message | `http://127.0.0.1:4466/overlay/featured` | 900 × 260 |
   | Viewer counter | `http://127.0.0.1:4466/overlay/viewers` | 600 × 120 |
   | Alerts | `http://127.0.0.1:4466/overlay/alerts` | 800 × 300 |

   Add `?theme=neon` (or any theme name) to give one source its own look. The Theme Studio's **Copy OBS address** buttons build these addresses for you.

> [!TIP]
> Use the `http://127.0.0.1:4466/...` addresses rather than local files. OBS 33's browser blocks pages opened as local files from reaching anything on `127.0.0.1`.

To check everything without going live, press **Send test to OBS** in the Theme Studio, or start OBS streaming to a test server on your own PC. CrossChat sees that a stream to `rtmp://127.0.0.1` is a test and doesn't start anything public.

**Prefer a zip?** `CrossChat-<version>-windows.zip` is still on every release. Extract it and double-click `Install.cmd`: it uses a Python 3.10+ already on your PC (or offers to install one), sets up its own environment, and asks for your channels in a console window. Then follow steps 3–5 above.

## Mac (beta)

There is a Mac download too. It's a **beta**: on every change, GitHub's Mac machines run the hub's tests, the Keychain storage, the OBS script's start-and-restart code (in LuaJIT, the Lua OBS uses) and a full install, start and uninstall from the download. **It has not yet been run with OBS on a real Mac.** Tell us what works and what doesn't in [Issues](https://github.com/RandyNorthrup/crosschat-obs/issues).

You need a recent macOS (tested on macOS 15 with Apple silicon, on GitHub's machines; Intel Macs are untested), OBS Studio 28 or newer, Chrome, Edge or Chromium, and Python 3.10 or newer from [python.org](https://www.python.org/downloads/macos/) or Homebrew (`brew install python@3.13`). The installer tells you if Python is missing; it doesn't install it for you.

1. **Download** `CrossChat-<version>-mac.zip` from **[Releases](https://github.com/RandyNorthrup/crosschat-obs/releases/latest)** and double-click it to unpack it.
2. **Double-click `Install.command`.** If macOS says it can't check the developer (the download isn't signed by Apple), open Terminal, type `bash ` with a space, drag `Install.command` into the window and press Return.
   It installs to `~/Library/Application Support/CrossChat`, sets up its own Python environment with checksum-verified packages, asks the same questions as on Windows, and adds an **Applications → CrossChat** folder (Open chat, Theme Studio, Try the demo, Go live on X, Uninstall).
3. **Add the script to OBS:** *Tools → Scripts → +*, press **Cmd+Shift+G**, paste the path the installer put on your clipboard (`~/Library/Application Support/CrossChat/obs/crosschat.lua`) and press Return.
4. **Add the extension:** `chrome://extensions` → **Developer mode** → **Load unpacked** → **Cmd+Shift+G** → `~/Library/Application Support/CrossChat/extension`.
5. **Widgets:** the same Browser Source addresses as on Windows.

What's different on a Mac:

- **Sign-ins** (Twitch, Kick, Rumble) are encrypted under a key CrossChat keeps in your login Keychain, instead of Windows' DPAPI. The uninstaller removes the key.
- **The chat window** is moved and closed through the browser's own AppleScript. The first time, macOS asks whether CrossChat (or OBS) may control your browser. If you say no, or macOS doesn't ask, windows still open where they should; CrossChat just can't move or close them afterwards (it tries again a minute later, so allowing it later works too). Opening a window also brings the browser to the front.
- **The phone companion** stays off until you choose the address. macOS doesn't tell apps whether a network is a private one, so CrossChat won't guess: on your home network, set `"remote": {"bind": "<your Mac's address>"}` in `config.json` (*System Settings → Wi-Fi → Details* shows the address).
- **Read-aloud** uses the Mac's own voices.
- **Uninstall:** Applications → CrossChat → **Uninstall CrossChat**. It offers to keep your settings and themes in `Documents/CrossChat backup`.

## Try it without going live

Start menu → CrossChat → **Try the demo**, or `python hub\hub.py --demo`. It opens the chat app on a made-up live stream with fictional chatters on Twitch, YouTube, Kick, X and TikTok, including questions, subs, raids, Super Chats and moving viewer counts.

Reply, moderate, star and feature messages as much as you like: in the demo everything "works", and nothing is posted anywhere. The demo runs on its own port (4477), so it never mixes with your real chat.

## Using it

| To | Do this |
|---|---|
| Open the chat window | Start OBS streaming (it opens by itself), or Start menu → CrossChat → **Open chat**, or the OBS hotkey |
| Answer everyone | Type in the box and press **Enter** |
| Answer one platform or one person | **only:** buttons, or hover a message → **reply** |
| Put a message on stream | Hover it → **show**. **Hide** in the window, or the hotkey, takes it off. |
| Restyle the widgets | ✎ in the chat window, or Start menu → CrossChat → **Theme Studio** |
| Go live on X now | Start menu → **Go live on X**, the OBS script's button, or the hotkey |
| Moderate | Open a message → **Moderate** (Twitch and Kick need **Connect Twitch** / **Connect Kick** in Settings once) |
| Use your phone | Settings (⚙) → **Pair a device**, then scan the QR code |
| Use another PC | Settings (⚙) → **Pair a device**, then open the address it shows in that PC's browser (enter the 6-digit code if asked) |

**Hotkeys** (OBS → *Settings → Hotkeys*, search "CrossChat"):
- Open chat window
- Go live on X
- Hide featured message

A Stream Deck can trigger them with a *Hotkey* action, or open the Start-menu shortcuts with *System → Open*.

**The OBS script panel** (*Tools → Scripts → crosschat.lua*) has buttons for all of the above, plus a dry run for X and **Start the hub again**.

**Dock the chat inside OBS.** In OBS: *Docks → Custom Browser Docks*, name it `CrossChat`, URL `http://127.0.0.1:4466/` (4466 is the `port` setting), then **Apply** and drag the dock where you want it. Use `127.0.0.1`, not `localhost`: `localhost` is the overlays' address and only serves the widgets. The dock reads chat, replies, puts messages on stream and moderates Twitch and Kick. Keep the CrossChat window in Chrome or Edge open as well (it opens by itself when you go live): it does the work on the YouTube, X, TikTok, Facebook, Instagram and Rumble pages, and it is the one that reads chat aloud.

### What each platform supports

| | Read chat | Reply | Moderate | Viewer count | Alerts |
|---|:-:|:-:|---|:-:|---|
| **Twitch** | ✅ | ✅ (official API once connected) | delete, timeout, ban, unban | ✅ | subs, resubs, gifts, raids, cheers |
| **YouTube** | ✅ | ✅ | remove, 5-minute timeout, hide user | ✅ | Super Chats, Super Stickers, members, gifted memberships |
| **Kick** | ✅ | ✅ (official API once connected) | delete, timeout, ban, unban | ✅ | subs, gifts, hosts (see [Known limits](#known-limits)) |
| **X** | ✅ | ✅ | — | ✅ | — |
| **TikTok LIVE** | ✅ (your own LIVE page) | ✅ | in TikTok | ✅ | gifts, follows, shares; likes and joins if you turn them on (see [Known limits](#known-limits)) |
| **Facebook Live** | ✅ (Live Producer) | ✅ | delete (the rest in Facebook) | ✅ | — |
| **Instagram Live** | ✅ (Live producer) | ✅ | in Instagram | ✅ | — |
| **Rumble** | ✅ (official API) | ✅ | delete, mute 5 minutes, mute for the stream, mute forever | ✅ | Rants, subs, gifted subs |

## X Live

X has no stream key that starts a livestream by itself: someone has to press **Go Live** on X Live Studio. CrossChat does it for you.

1. In [X Live Studio](https://studio.x.com/live), create a source (CrossChat expects it to be called **OBS**; change `x.source` if yours has another name) and send OBS's video to it with your multistream setup.
2. Run `Install.cmd` and answer **yes** to "Do you stream to X?", or set `"x": {"enabled": true}` in `config.json`.
3. When OBS starts streaming, CrossChat waits a few seconds, opens Live Studio next to the chat window, and the extension:
   - checks the source shows **Connected**;
   - fills in the title;
   - sets the audience to **Public**;
   - presses **Go Live**.

   A banner at the top of the X page shows each step. The chat window says **X: live.**, or where it stopped.
4. When OBS stops, the X livestream is ended about 15 seconds later, so a quick stop and start in OBS doesn't end it.

The extension only acts in the two minutes after the hub asks it to, so opening or reloading the X page yourself never starts a stream. To rehearse:
- **Test X (never goes live)** fills in the form without pressing Go Live.
- `hub\control.py x-private` (in the CrossChat folder) goes live visible to you only.

Turn off the automatic start with `"auto_go_live": false` and use **Go live on X** when you want it.

## TikTok LIVE

TikTok has no public chat API. Tools that connect to TikTok LIVE chat directly usually do it through an outside "signing" service (Euler Stream is the common one), which learns which live you're reading; you only hand it your TikTok session if you sign in through it to send messages. CrossChat uses no outside service: it reads your own LIVE page in your own browser.

1. Set `"tiktok": "@yourname"` in `config.json` (or answer the installer's question).
2. Stay signed in to TikTok in Chrome or Edge, the browser with the CrossChat extension.
3. When OBS starts streaming, CrossChat opens **your own TikTok LIVE page** in a small window under the chat window. Keep it open while you stream.
4. The extension passes on the chat lines shown there and types your replies into TikTok's own chat box, as you. Replies are up to 150 characters.
5. Gifts, follows, shares and likes shown on that page become CrossChat alerts:
   - **Gifts** show the gift's name and how many, such as "Rose ×5". A combo counts as one alert with its final count. TikTok's page doesn't show what a gift costs, so CrossChat doesn't make up a money value.
   - **Follows** show once a stream per viewer, and **shares** at most once a minute per viewer.
   - **Likes** are added up per viewer and shown once they stop liking. When many viewers' likes come in at once, they show as one line, such as "12 viewers liked the LIVE ×340". Likes stay off the on-stream alerts and read-aloud unless you turn them on in Theme Studio.
   - **Joins** are off. To see who joins, turn on Settings → Filters → **Show who joins your TikTok LIVE**.

   Only rows TikTok itself marks as gifts, follows and the like count. A viewer who types "followed the host" or "×99" in chat can't fake an alert.

The extension first asks CrossChat which TikTok account is yours. On every other TikTok page, someone else's LIVE included, it reads nothing. Moderate TikTok chat in TikTok itself.

## Facebook Live and Rumble

**Facebook Live.** Set `"facebook": true` (or answer the installer's question). When OBS starts streaming, CrossChat opens Facebook's **Live Producer**, where you press Go live as usual. While your live runs, the extension passes on the comments shown there and types your replies into its comment box, as you. Live Producer only ever shows your own broadcasts, and the extension may touch no other part of Facebook.

**Rumble.** In Settings → Connections → Rumble, paste your **Live Stream API URL** from [rumble.com/account/livestream-api](https://rumble.com/account/livestream-api). CrossChat reads Rumble chat, Rants, subs, gifted subs and the viewer count through Rumble's official API, and keeps the URL encrypted on this PC. When your Rumble live starts, CrossChat opens Rumble's chat window for it, and replies are typed there as you (sign in to Rumble in the same browser). The extension never presses Rumble's Rant button.

**Deleting Facebook comments.** In the CrossChat window, a Facebook comment's menu has **Delete comment**. The extension opens that comment's own menu in Live Producer, picks Delete and confirms Facebook's question, as you. It finds the comment by the id Facebook gave it, so it can't delete a different one. Hiding comments and banning people are still done in Facebook itself.

**Moderating Rumble chat.** A Rumble message's menu in the CrossChat window has **Delete message**, **Mute 5 minutes**, **Mute for this stream** and **Mute forever**: the same choices Rumble gives the streamer. The extension uses Rumble's own "Moderate this comment" menu in the chat window CrossChat opened, as you. Rumble's API gives chat lines no id, so the extension picks the newest line with that sender's name and those exact words. To answer Rumble's "delete this message?" question, a few lines of the extension run inside Rumble's chat page and say yes to that one question, once, right after CrossChat asks; every other question is left to you. Unmute people under **Muted users** in Rumble's chat.

## Discord

CrossChat can post to one channel of your Discord server while you're live. It only posts: nothing is read from Discord.

1. In Discord: **Server Settings → Integrations → Webhooks → New Webhook**. Pick the channel, then **Copy Webhook URL**.
2. In CrossChat: Settings → Connections → Discord, paste it and press **Connect Discord**. CrossChat checks it with Discord and keeps it encrypted on this PC; it's never shown again.
3. Pick what goes there: **a going-live notice** (with links to your channels), **messages you show on stream**, and **all chat** (off at first). **Send a test post** checks the channel.

Only what viewers already see on stream is posted, never messages your filters hid. Chat can't ping anyone there (`@everyone` included), and links in chat show as text that can't be clicked. Posts are spaced at least 2 seconds apart, chat lines are grouped into one post, and CrossChat waits whenever Discord asks it to. Nothing is posted during a test stream to this PC.

## The companion away from home (Tailscale)

The companion is for your home network. To use it from anywhere, for example on your phone while streaming IRL or from a friend's place, use [Tailscale](https://tailscale.com): a private, encrypted network between your own devices, free for personal use.

1. Install Tailscale on the streaming PC and sign in.
2. Install the Tailscale app on your phone and sign in to the **same account**. Leave it on.
3. In CrossChat: Settings → Paired devices → switch on **Away from home too, with Tailscale**. It shows your PC's Tailscale address, or says what's missing.
4. Press **Pair a device** and scan the QR code. With Tailscale on, the code uses the PC's Tailscale address, so it works at home and away. A phone you paired before needs pairing once more.

Pairing is still required, and the companion listens only on the address Windows has on Tailscale's own adapter. When Tailscale stops, the companion stops listening there; it comes back with Tailscale.

## Instagram Live

Instagram takes a stream from OBS through its **Live producer** on instagram.com (**Create → Live video**), which gives you a stream URL and key.

1. Set `"instagram": true` in `config.json` (or answer the installer's question), and stay signed in to Instagram in Chrome or Edge, the browser with the CrossChat extension.
2. In the Live producer, use a **persistent stream key** (**Manage Persistent Key**) in OBS, so the same key works every time you go live.
3. When OBS starts streaming, CrossChat opens instagram.com in a small window under the chat window. Open **Create → Live video** there, add a title and pick the audience, press **Next**, and press **Go live** once the preview shows.
4. While the live runs, the extension passes on the comments and viewer count the Live producer shows, and types your replies into its comment box, as you.

Start the live in the window CrossChat opens (or any tab opened at instagram.com's home page): the extension works only there. The Live producer only ever shows your own live, and the extension reads nothing else on Instagram: no feed, messages or profiles. To rehearse, pick the **Practice** audience, which only you can see. Moderate Instagram comments in Instagram itself.

## Settings

Your settings are in `%LOCALAPPDATA%\CrossChat\config.json` (start from [`config.example.json`](config.example.json)). Restart OBS after changing them.

| Key | Default | |
|---|---|---|
| `twitch`, `youtube`, `kick` | `""` | Your channels. A name, an `@handle`, a channel ID or a link all work. |
| `tiktok` | `""` | Your TikTok `@name`. Its LIVE page opens in your browser when OBS goes live (see [TikTok LIVE](#tiktok-live)). |
| `tiktok_window` | `"auto"` | Where that page goes: under the chat window, or `{"x", "y", "width", "height"}`. |
| `facebook` | `false` | `true`: Facebook Live comments from Live Producer (see [Facebook Live and Rumble](#facebook-live-and-rumble)). |
| `instagram` | `false` | `true`: Instagram Live comments from its Live producer (see [Instagram Live](#instagram-live)). |
| `facebook_window`, `instagram_window`, `rumble_window` | `"auto"` | Where Live Producer, instagram.com and Rumble's chat window go. |
| `port` | `4466` | The hub's port on `127.0.0.1`. The extension expects 4466. |
| `browser` | `"auto"` | `"auto"` (Chrome, else Edge), `"chrome"`, `"edge"` or a full path. It must be the browser that has the extension. |
| `window` | `"auto"` | `"auto"` docks the chat at the right edge of the main screen, or `{"x", "y", "width", "height"}`. Put it where OBS doesn't capture. |
| `open_window_on_stream_start` | `true` | Open the chat window when OBS starts streaming. |
| `close_window_seconds_after_stream` | `120` | How long it stays after the stream ends. |
| `overlay.platforms` | `"all"` | Which platforms the on-stream chat shows by default, for example `["twitch"]`. |
| `overlay.theme` | `"classic"` | The theme sources use without `?theme=` (the Theme Studio's **Set as default** overrides it). |
| `obs.host`, `obs.port`, `obs.password` | from OBS | Only if OBS's WebSocket isn't on this PC or you want to override what OBS has saved. |
| `remote.enabled`, `remote.port` | `true`, `4467` | The companion for paired devices. It only starts listening once you pair a device, and never on a network Windows calls Public. |
| `remote.tailscale` | `false` | Also listen on your PC's Tailscale address, for the companion away from home (see [above](#the-companion-away-from-home-tailscale)). The switch in Settings → Paired devices sets it. |
| `remote.bind` | `"auto"` | Where the companion listens on the home network. `"auto"` is your PC's home-network address. |
| `updates.check` | `false` | `true`: ask GitHub once a day whether a newer CrossChat is out, and show a link to it. Nothing about you is sent. The switch in Settings → About sets it. |
| `twitch_client_id` | CrossChat's | Use your own Twitch app instead (a Public client from dev.twitch.tv). |
| `kick_client_id`, `kick_client_secret` | CrossChat's | Use your own Kick app instead (redirect URL `http://localhost:4466/kick/callback`). |
| `emotes` | all on | `{"bttv": true, "ffz": true, "7tv": true}`: third-party emotes in the chat and widgets. |
| `logs.enabled`, `logs.keep_days` | `true`, `90` | Keep each stream's chat on this PC, and for how long. |
| `custom_overlays` | `""` | A folder of your own overlay pages, served at `http://localhost:4466/custom/<file>` (see below). |
| `x.enabled` | `false` | Use X Live. |
| `x.auto_go_live` | `true` | Go live on X when OBS starts streaming. |
| `x.title` | `"Live now"` | Livestream title. |
| `x.title_file`, `x.title_prefix` | `""` | Use the first line of a text file as the title instead (handy with a "now building" file). |
| `x.source` | `"OBS"` | The source name in X Live Studio. |
| `x.end_with_obs` | `true` | End the X livestream when OBS stops. |

### Your own overlays

Hand-made overlay pages can read CrossChat's live feed: `/events` (Server-Sent Events) and `/settings`.

Since OBS 33, a page added as a *local file* can't reach `127.0.0.1`, so let CrossChat serve it:
1. Set `"custom_overlays": "C:\\path\\to\\your\\overlays"` in `config.json`.
2. Use `http://localhost:4466/custom/your-page.html` as the Browser Source URL. (`http://127.0.0.1:4466/custom/...` is sent there.)

These pages get their own address, which the browser keeps apart from the CrossChat window, so an overlay you downloaded can show chat but can't reply, moderate or change anything as you.

Subfolders, images, fonts, video and audio work. Nothing outside that folder is served. To build your own, see the **[API](docs/API.md)**.

## How it works

```mermaid
flowchart LR
  OBS["OBS Studio<br/>crosschat.lua"] -- starts --> HUB
  OBS -- "stream started / stopped<br/>(obs-websocket)" --> HUB
  subgraph PC["Your PC (127.0.0.1 only)"]
    HUB["CrossChat hub<br/>hub.py"]
    WIN["Chat window"]
    WID["Widgets in OBS<br/>chat · featured · viewers · alerts"]
    EXT["Browser extension"]
  end
  TW["Twitch chat"] --> HUB
  YT["YouTube chat"] --> HUB
  KI["Kick chat"] --> HUB
  PH["Phone or other PC<br/>(paired, home network)"] <-- "chat app, port 4467" --> HUB
  HUB -- live feed --> WIN
  HUB -- live feed --> WID
  WIN -- "replies, mod jobs" --> EXT
  HUB -- "Twitch and Kick replies, moderation<br/>(official APIs)" --> TW & KI
  EXT -- posts as you --> YT & XS["X Live Studio"]
  XS -- "X chat, viewers" --> EXT --> HUB
  HUB -- "go live / end" --> EXT
```

When you pair a device, Windows asks once whether Python may use the network. Choose **Allow** for private networks.

- **The hub** (`hub/hub.py`) is a small Python program. It reads each platform's public chat and follows OBS through its WebSocket server. It serves the chat window, the widgets and the Theme Studio, on `127.0.0.1` only.
- **The OBS script** (`obs/crosschat.lua`) starts the hub with OBS and gives you buttons and hotkeys.
- **The extension** (`extension/`) does what only your signed-in browser can do: post your YouTube and X replies, moderate YouTube, and work X Live Studio. It reads no logins and has no Chrome permissions.

## Privacy and security

CrossChat has no server and no account. Everything runs on your PC and talks straight from it to the platforms you set up, plus a few named helpers: decapi.me as a fallback for the Twitch viewer count (it's sent your channel name), the 7TV, BetterTTV and FrankerFaceZ emote services unless you turn them off, and, only if you switch them on, Discord and GitHub's update check. **[SECURITY.md](SECURITY.md) lists every connection it makes and what is sent.**

- The hub listens on `127.0.0.1` only and answers only under that address. Other websites get nothing from it, not even the chat, and can't put the CrossChat window in a frame.
- Your own overlay pages run at their own address and get only the public chat: they can't reply, moderate or change anything as you.
- Anything that *does* something (opening windows, going live, featuring a message, changing settings) is refused when another website asks for it.
- **Reading chat** uses the platforms' public, signed-out chat feeds.
- **Twitch and Kick replies and moderation** use their official APIs once you connect them in Settings.
  - The tokens are encrypted for your Windows account (DPAPI), or on a Mac under a key in your login Keychain. Disconnecting deletes them and revokes them at Twitch or Kick.
- **The extension reads no logins.** It has no Chrome permissions; it only types your YouTube and X replies into those sites' own chat boxes.
- **The companion port (4467)** only opens after you pair a device, and only on a network Windows calls Private, or on your own Tailscale address if you switch that on.
  - It answers paired devices only: an HttpOnly cookie per device, of which only a hash is stored.
  - Pairing codes are 6 digits, last 5 minutes and allow 5 tries.
  - Use it on your home network only.
- **Chat history** stays in `%LOCALAPPDATA%\CrossChat\logs` and is removed after 90 days. Spreadsheet exports can't run formulas a viewer typed.
- **Text-to-speech** uses Windows' own voices unless you pick one marked *online*.
- CrossChat reads OBS's WebSocket password from OBS's own settings file. It doesn't copy it anywhere.
- No telemetry and no analytics. Update checks only if you switch them on (Settings → About): then CrossChat asks GitHub once a day and sends nothing about you.
- Every release has a signed build provenance attestation: `gh attestation verify <zip> --repo RandyNorthrup/crosschat-obs`. The installer installs the exact Python packages CrossChat was tested with, checked against their checksums.

More detail, and how to report a problem privately: [SECURITY.md](SECURITY.md).

## Troubleshooting

| Problem | What to check |
|---|---|
| A message box says CrossChat can't reach OBS's WebSocket server | OBS → *Tools → WebSocket Server Settings* → tick **Enable WebSocket server**. CrossChat connects by itself once it's on. |
| Widgets show nothing | Is OBS open with `crosschat.lua` loaded? Press **Start the hub again** in *Tools → Scripts*. Use the `http://127.0.0.1:4466/...` address, not a local file. |
| "Replies go out through the CrossChat extension, and it is not active" | Load the extension (Install step 4), then close the chat window and open it again. |
| A reply to one platform failed | The chat window says why (not signed in, message too long, chat not open). YouTube replies need you signed in to YouTube in the same browser. |
| X stopped at a step | The X page banner and the chat window name the step. Finish by hand; if it keeps happening, X may have changed its page, so [open an issue](https://github.com/RandyNorthrup/crosschat-obs/issues). |
| Anything else | `%LOCALAPPDATA%\CrossChat\crosschat.log`, and the OBS log (*Help → Log Files*, lines with `crosschat.lua`). |

## Known limits

- **Mac is a beta.** Everything but OBS itself is tested on macOS by GitHub's Mac machines; it hasn't been run with OBS on a real Mac yet. See [Mac (beta)](#mac-beta) for what differs.
- **Kick** replies and moderation use Kick's documented API. Sign-in was verified against Kick; the post and moderation calls are covered by tests, not yet by a live Kick stream. Kick alerts come from Kick's public feed and haven't been checked against a real Kick stream yet.
- **Facebook Live** (new in 1.6) is read from Live Producer, so a redesign by Facebook can break it until CrossChat is updated. It was built and tested on a real "Only me" Facebook live.
- **Instagram Live** (new) is read from Instagram's Live producer, so a redesign by Instagram can break it until CrossChat is updated. Reading comments was built against a real "Practice" Instagram live; replies are typed into the same comment box and were tested on a copy of that page, not yet on a real live. The extension recognises the live, the viewer count and your own comments by Instagram's English labels.
- **Rumble** is read through Rumble's official API, which gives the latest 50 messages; CrossChat asks every 5 seconds, so a very busy Rumble chat can miss lines. Replies and **Delete** were tested on a real (unlisted) Rumble live; the mutes reached Rumble's server, which refused the only test possible (muting yourself), so muting someone else hasn't been seen working yet. Rumble's chat window has to stay open while you're live.
- **Facebook comment delete** was tested on a real Live Producer live (with the streamer's own comment). Deleting a viewer's comment uses the same menu but hasn't been seen on a real live yet.
- **TikTok LIVE** is read from TikTok's own LIVE page, so a redesign by TikTok can break it until CrossChat is updated. Gift, follow, share and join rows were checked against a real public TikTok LIVE; the whole path hasn't run on a streamer's own TikTok LIVE yet (TikTok lets accounts go LIVE from 1,000 followers).
- **X Live** depends on X Live Studio's page and needs X Premium. CrossChat clicks through it like a person would, so a redesign by X can break it until CrossChat is updated.
- **YouTube** chat is read the same way YouTube's own chat pop-out reads it.
- **YouTube moderation** clicks through YouTube's own chat menu in the CrossChat window, so the signed-in account must own the channel or moderate it. It hasn't been checked against a live YouTube stream yet.
- **Twitch and Kick moderation and replies** use their documented APIs. Sign-in and token handling were verified against Twitch and Kick. The individual ban, delete and post calls are covered by tests, not yet by moderating a real viewer on a live channel (that needs a second account in the chat).
- **The companion** uses plain `http` on your home network, like a router's own page. Don't forward its port. For away-from-home use, switch on [Tailscale](#the-companion-away-from-home-tailscale).
- **Twitch and merged chat on stream:** Twitch's written simulcasting rules still say not to show other platforms' chat on a Twitch stream, but in February 2026 Twitch's CEO said Twitch won't take enforcement action against creators for showing combined chat. Until the written rules change, the choice is yours: `"overlay": {"platforms": ["twitch"]}` (or `?platforms=twitch` on one source) shows Twitch chat only. Reading every chat in the CrossChat window yourself is fine either way.

## Uninstall

Start menu → CrossChat → **Uninstall CrossChat**, or *Settings → Apps → CrossChat → Uninstall* (on a Mac: Applications → CrossChat → **Uninstall CrossChat**). It offers to keep your settings and themes in `Documents\CrossChat backup`.

Then remove the two pieces it can't:
- the script in OBS (*Tools → Scripts*, select it, **−**);
- the extension in your browser.

## Development

```powershell
python -m pip install -r hub/requirements.txt pytest ruff
python hub/hub.py --test --twitch <any live channel>     # run the hub without OBS, against real chat
ruff check hub scripts tests
python -m pytest                                         # 63 tests: config, platforms, web server, obs-websocket, companion, 1.4 features and safety rules
node --test "tests/js/*.test.mjs"                        # 35 tests: theme engine, chat app, emotes and chat delay
python scripts/obs_e2e.py --obs <portable OBS folder>    # end to end against a real OBS (see the file)
pwsh scripts/package.ps1                                 # builds dist\CrossChat-<version>-windows.zip
python scripts/package_mac.py                            # builds dist/CrossChat-<version>-mac.zip (any system)
```

`pip install lupa` (on a Mac: `brew install luajit`) adds the OBS script tests (`tests/test_obs_script.py`): they run `obs/crosschat.lua` in LuaJIT with a stand-in for OBS and check that it starts the hub and restarts a crashed one, on Windows and on a Mac. On a Mac, `bash scripts/install.sh` installs from a checkout.

`scripts/obs_e2e.py` sets up a throwaway portable OBS with the script and the four widgets. It streams to an RTMP receiver on your PC (ffmpeg) and checks 19 things, from the script starting the hub to the hub leaving when OBS closes. It never touches your own OBS. Version 1.0.0 passed all 19 on OBS 33.0.1.

## Code signing policy

From 1.7.2, the Windows setup program is signed with [Azure Artifact Signing](https://learn.microsoft.com/azure/artifact-signing/) under the maintainer's Microsoft-verified identity (publisher **Randy Northrup**). Every download, signed or not, can also be checked with its GitHub build provenance attestation (see [SECURITY.md](SECURITY.md#checking-a-download)).

- **Committers and reviewers:** [Randy Northrup](https://github.com/RandyNorthrup)
- **Approvers:** [Randy Northrup](https://github.com/RandyNorthrup)
- Every release is built by GitHub Actions from this repository's source. Nobody signs anything built elsewhere.
- Signing happens inside the release workflow, from a GitHub environment only `v*` tags can use. No signing password or key is stored anywhere: Azure accepts GitHub's short-lived sign-in token from that environment only, and that identity can do nothing but sign. The workflow checks the signature and its timestamp before publishing.

**Privacy policy:** CrossChat will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it. It talks only to the chat platforms you set up, to decapi.me as a fallback for the Twitch viewer count (with your channel name) and, unless you turn them off in the installer or `config.json`, to 7TV, BetterTTV and FrankerFaceZ for emote pictures. Only if you switch them on: Discord, through the webhook you connect, and GitHub, once a day, for the update notice. The full list of connections and what each one sends is in [SECURITY.md](SECURITY.md#what-leaves-your-pc).

## Credits

- Platform icons: [Simple Icons](https://simpleicons.org) (CC0). The platform names and logos belong to their owners.
- See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

CrossChat isn't affiliated with or endorsed by OBS Project, X Corp., Twitch, YouTube or Kick.

## License

[MIT](LICENSE) © 2026 Randy Northrup
