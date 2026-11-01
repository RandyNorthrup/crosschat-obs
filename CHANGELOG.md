# Changelog

All notable changes to CrossChat are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- **Mac:** the hub no longer gets a copy of everything OBS has open. The OBS script started it with all of OBS's files and sockets, OBS's WebSocket server among them, so after OBS closed the hub kept OBS's WebSocket port taken (about 20 seconds in our tests), and an OBS opened again in that time couldn't start its WebSocket server (CrossChat then couldn't follow it). Found with OBS 33.0.1 on macOS 15.
- **Mac:** the chat window's notice said "Start menu → CrossChat → Open chat"; on a Mac it now names Applications → CrossChat in the home folder. The Paired-devices hint about Windows' network question no longer shows on a Mac, and the Theme Studio's look button says "follows this device", not "follows Windows".
- The chat window styled a first-time chatter's **1ST** flag and line like the Settings "Set up your channels" note (a padded, bordered box), so the flag stood out of the line as a large pill and stretched the **Q** flag beside it. Seen in OBS's dock on a Mac; the same on Windows.
- **Mac:** the README and the installer say where the Applications → CrossChat folder is (the Applications folder in your home folder, not Finder's main one), and that `Install.command` has to be started from Terminal: macOS 15 refuses to open it with a double-click, because the download isn't signed by Apple.

### Changed

- **Mac is checked with real OBS.** CrossChat 1.7.1 and this version were run with OBS 33.0.1 on macOS 15.7.4 (Intel Mac mini) and 15.7.9 (Intel MacBook Pro): download and checksum, installer, the OBS script and the hub following OBS, the four widgets and the chat docked inside OBS, the login Keychain, the extension in Chrome 156, and the uninstaller. The README's Mac section lists exactly what; Apple silicon with OBS, moving and closing windows through the browser, read-aloud and the companion are still a beta there.
- The real-OBS check (`scripts/obs_e2e.py`) runs on a Mac too, with the installed OBS.app and a stand-in home folder, so your own OBS settings are never touched. It also checks that OBS's own browser shows the four widgets and the docked chat (with test chat in it), and that OBS's WebSocket port is free once OBS closes. `--crosschat` tests an installed copy, `--ffmpeg` names the RTMP receiver, and the logs are kept when something fails.
- The hub's start line in `crosschat.log` names the Python running it.
- The README says what to do when the CrossChat dock in OBS says "Couldn't load that page!" (OBS opened it before CrossChat was ready: press "Click here to retry"), and that OBS on a Mac needs the Input Monitoring permission for hotkeys while another app is in front.

## [1.7.2] - 2026-11-01

### Security

- The Windows setup program is code-signed by Randy Northrup with Azure Artifact Signing, timestamped. The release workflow signs it with no stored secret (GitHub's OIDC token, trusted only from a tag-only "release" environment) and checks the signature before publishing. This replaces the planned SignPath Foundation signing.

### Fixed

- The README's privacy list said CrossChat makes no update checks; since 1.7 it makes one a day if you switch it on.

## [1.7.1] - 2026-10-31

### Added

- The chat window says when the browser is still running an older CrossChat extension, and how to reload it. After an update Chrome and Edge keep the old extension's code until it is reloaded in `chrome://extensions`, so 1.7's Rumble moderation and Instagram didn't work until then.

### Fixed

- docs/INSTALLER.md lists the Discord webhook (`discord.bin`) among what an update keeps, and says to reload the extension afterwards.

## [1.7.0] - 2026-10-31

### Added

- **A setup program**, `CrossChat-Setup-<version>.exe`, now the normal way to install on Windows. See [docs/INSTALLER.md](docs/INSTALLER.md).
  - Installs for your Windows account only, needs no administrator rights, and brings its own Python (python.org's embeddable package), so there's nothing else to install.
  - No console windows. It shows a privacy page, asks before switching on OBS's WebSocket server, and adds CrossChat to *Settings → Apps* with an uninstaller.
  - It keeps your settings, themes, sign-ins and chat history on update.
  - Built in the release workflow from pinned, checksum-checked downloads, with a build provenance attestation like the zip. The zip with `Install.cmd` is still published.
- **Settings → Channels & options**: set your channels and options in the CrossChat window instead of `config.json`. Every value is checked, the file is replaced in one step with a `.bak` kept, and the window says which changes need OBS restarted.
- **Viewer cards**: click a name to see when they first chatted, how many messages, their lines this stream and in earlier streams (searchable), with read-aloud, filter and moderation at hand.
- **Instagram Live comments**, read from Instagram's live producer on instagram.com, with replies typed into its comment box. Set `"instagram": true`, answer the installer's question, or switch it on in Settings.
- **Moderation on Facebook and Rumble** from the CrossChat window, through each site's own menus, as you:
  - Facebook: delete a comment (Live Producer's own menu).
  - Rumble: delete a message, mute for 5 minutes, mute for this stream, or mute forever (Rumble's own "Moderate this comment" menu).
- **TikTok gifts, follows, shares and likes as alerts**, from your own TikTok LIVE page. A gift shows its name and count, one alert per combo; TikTok's page shows no prices, so none are made up. Likes are added up per viewer and stay off on-stream alerts unless you turn them on. Joins are off; turn them on in Settings → Filters. A viewer can't fake an alert by typing "followed the host" or "×99".
- **One alert wording for every platform**, shared by the widgets, the on-stream chat and the window. Rumble Rants and YouTube Super Stickers get their own alert types and switches.
- **Discord**: post a going-live notice, the messages you show on stream, or all chat to a channel of your server through a webhook. No bot and no sign-in. Chat can't ping anyone, and hidden messages never go. The webhook is kept encrypted and never shown again.
- **The companion away from home, with Tailscale** (Windows): one switch in Settings → Paired devices. Pairing is still needed, and it listens only on your PC's own Tailscale address, never on an address that merely looks like one.
- **Update notice**, off unless you switch it on (installer or Settings → About): once a day CrossChat asks GitHub whether a newer version is out and shows a link to its release page. Nothing about you is sent, and nothing is downloaded.
- **Mac (beta)**: a macOS download with `Install.command`. Sign-ins are encrypted under a key in your login Keychain, and the chat window is placed through your browser. It's tested on macOS in CI (tests, a full install, start and uninstall), but not yet with OBS on a real Mac.
- The installer shows what CrossChat connects to, and asks whether to use 7TV, BetterTTV and FrankerFaceZ emotes.
- A code signing policy in the README, for signing releases through SignPath Foundation (application in progress).
- The README shows how to dock the chat window inside OBS (Docks → Custom Browser Docks), and the real-OBS check now runs with it docked.

### Fixed

- The README's table of what each platform supports still said Facebook and Rumble are moderated only on the platform, and that TikTok has no alerts.

- Facebook and Rumble messages carried no moderation id, so moderation menus for them couldn't work.
- A Rumble reply could stall when Rumble kept its Send button off; the text is now typed the way a person types.
- TikTok chat lines could be missed when TikTok reused a row on the page, or when more than 50 short lines arrived at once.
- In a checkout, git now ignores every `.bin` file in the folder, so an encrypted sign-in like `rumble.bin` can't be committed by accident.

### Security

- requests 2.34.2 (was 2.32.5), for GHSA-gc5v-m9x4-r6x2: an insecure temporary file in requests' `extract_zipped_paths()`. CrossChat doesn't call it; updated anyway.
- The update notice's link is rebuilt from CrossChat's own GitHub address and the version's numbers, so no text from the hub's message reaches the link (found by CodeQL; the address was already checked exactly).

### Changed

- The OBS script runs CrossChat with the setup program's Python when it's there, then the one `Install.cmd` made, then the Python launcher. The script's own Python field still comes first. Its start-and-restart code is now tested in LuaJIT on Windows and macOS.

## [1.6.0] - 2026-10-31

### Added

- **Facebook Live comments**, from Live Producer in your browser, with replies typed into its comment box.
  - Set `"facebook": true`, or answer the installer's question. CrossChat opens Live Producer when OBS goes live.
  - The extension may touch only `facebook.com/live/producer`, which only ever shows your own broadcasts.
- **Rumble chat, Rants, subs and gifted subs** through Rumble's official Live Stream API, with replies.
  - Paste your API URL in Settings → Connections → Rumble. It's kept encrypted for your Windows account and never shown again.
  - When your Rumble live starts, Rumble's chat window opens for it, and replies are typed there as you. The extension never presses the paid Rant button.
- Facebook and Rumble show everywhere: chat window, companion, widgets, Theme Studio, history, read-aloud and filters.

## [1.5.0] - 2026-10-31

### Added

- **TikTok LIVE chat**, read from your own TikTok LIVE page in your browser, with replies typed into TikTok's own chat box.
  - Set `"tiktok": "@yourname"`. CrossChat opens your LIVE page when OBS goes live.
  - No outside signing service and no TikTok login leaves your browser. On every other TikTok page the extension reads nothing.
  - TikTok shows in the chat window, the companion, the widgets (with its logo and viewer count), the Theme Studio and the history.
- **CrossChat repairs itself.**
  - A chat message a platform sends that CrossChat can't read is skipped; the rest of the chat carries on.
  - A platform connection that fails on something unexpected starts again by itself, and the problem goes in the log.
  - If CrossChat itself stops with an error, the OBS script starts it again within seconds (up to 5 times in 10 minutes).
- Measured: 30,000 chat messages at 1,000 a second reached every widget, in order, with none lost or doubled and a median delay of about 1 ms.

### Changed

- The extension may now also touch `www.tiktok.com`, only for your own TikTok LIVE page.
- Kick's chat connection notes in the log why it dropped.

## [1.4.0] - 2026-10-31

### Added

- **Kick replies and moderation** through Kick's official API. **Connect Kick** in Settings signs in with Kick's OAuth 2.1 and PKCE.
  - Reply to everyone, to Kick only, or to one Kick viewer as a threaded reply.
  - Delete, timeout (1 minute to 7 days), ban and unban.
  - The token is encrypted for your Windows account (DPAPI). Disconnecting revokes it at Kick.
- **7TV, BetterTTV and FrankerFaceZ emotes** in the chat window, the companion and the widgets: the global sets and your Twitch channel's. Turn each off with `"emotes"` in `config.json`.
- **Read chat aloud** (text-to-speech): questions only, everything, alerts, a `!tts` command, or the featured message.
  - It uses Windows' own voices. Voices that send text online are marked as such.
  - Links, emote names, filtered messages and your own lines are never read.
  - Paired devices can read a message aloud or skip one.
- **Filters**: hide words, viewers, chat commands and well-known bots from the widgets, without deleting anything on the platform.
  - **Filter this user** in a message's menu. New filters also take matching messages already on screen off the stream.
  - Hidden messages stay in your window, dimmed, with the reason.
- **Chat delay** for the on-stream chat (`chat.delay` in the Theme Studio, or `?delay=` on one source): a message deleted, timed out or filtered while it waits never reaches the stream. The featured message is never delayed.
- **First-time chatters** are marked: first message ever in your channel (Twitch says so) or first this stream.
- **Connection health**: how long each platform has been connected, its last message and its reconnects.
- **Chat history**: every stream's chat is kept on your PC for 90 days. Search it, filter by platform or questions, and export it as CSV or HTML (Settings → Chat history).
- New screenshots: text-to-speech, filters, chat history and connection health.
- **[API documentation](docs/API.md)** for your own overlays and tools.
- Release downloads come with a signed **build provenance attestation**: `gh attestation verify <zip> --repo RandyNorthrup/crosschat-obs`.

### Changed

- **The extension reads no logins any more.** It has no Chrome permissions at all. Twitch replies go through Twitch's API only, so connect Twitch in Settings to reply there.
- **Companion**: it listens only on your PC's home-network address, and refuses to start on a network Windows calls Public (café or hotel Wi-Fi). It closes when the PC moves to another network. `"remote": {"bind"}` sets the address yourself, for Tailscale.

- **Your own overlays** are served at `http://localhost:4466/custom/` (old `127.0.0.1` addresses are sent there). See Security.

### Security

An independent review of the whole codebase found the issues below. All are fixed.

- **Other websites get nothing from CrossChat.** Before, any website open in your browser could read the chat feed and, from `/events`, paired devices' names, quick replies and sign-in state. It could also take over the reply and speech roles of the CrossChat window.
- **The CrossChat window, the Studio and the pairing page can't be framed** by another site, where a hidden frame could take your clicks. If a second window takes the reply or speech role and closes, the role goes back to the window that had it.
- **Your own overlay pages can't act as you.** They run at their own address and get the public chat only, without filtered messages or CrossChat's notes. Before, a downloaded overlay pack could post, moderate and read history.
- **The widgets only load CrossChat's own files**, emote pictures and Google Fonts. A shared theme's custom CSS can't call other servers.
- **Companion:**
  - it answers only requests addressed to an IP address, which stops DNS-rebinding pages from trying pairing codes;
  - it stays off when Windows can't say the network is Private;
  - it closes when no device is paired;
  - oversized or slow requests are dropped, and connections at once are limited.
- **Filtered messages** can't be featured or read aloud, from any device.
- **Disconnect** revokes both Kick tokens the way Kick documents it, and says so when Twitch or Kick didn't confirm.
- Twitch's sign-in page is only ever opened on twitch.tv.
- A strange viewer count from a platform can't break the chat feed any more.
- Requests from other sites on the same address (`same-site`) are treated like any other website.
- Emote names and picture addresses from 7TV, BetterTTV and FrankerFaceZ are checked before any page sees them.
- Chat history exports neutralise spreadsheet formulas a viewer could type.
- **Supply chain:**
  - the installer installs exact package versions checked against their SHA-256 hashes (`hub/requirements.lock`);
  - GitHub Actions are pinned to commits;
  - releases are built by a job that installs nothing.
- Your chat history, tokens and settings are kept out of git when running from a checkout.
- [SECURITY.md](SECURITY.md) now lists every connection CrossChat makes and what it sends.

## [1.3.0] - 2026-10-31

### Added

- **Demo mode**: Start menu → CrossChat → **Try the demo**, or `hub.py --demo`.
  - A made-up live stream on every platform, with questions, alerts and moving viewer counts.
  - Replies, moderation, stars and featured messages all "work", and nothing is posted anywhere.
  - It runs on its own port (4477) and never mixes with your real chat.
- **Videos** in the README and `assets/video/`: an overview, the companion on a phone, the Theme Studio, and the widgets recorded in OBS 33.0.1.
- Companion guide: a section on using it from **another PC**, including its own app window in Chrome or Edge.

## [1.2.0] - 2026-10-31

### Added

- **Your own overlays**: `"custom_overlays"` in `config.json` names a folder whose pages CrossChat serves at `http://127.0.0.1:4466/custom/...`.
  - OBS 33 no longer lets an overlay opened as a local file read CrossChat's live feed. This is the way around that.
  - Only files inside that folder, of overlay kinds (pages, styles, scripts, images, fonts, video, audio), are served.

## [1.1.0] - 2026-10-31

### Added

- **Companion**: the chat app on a phone, tablet or another PC on your home network.
  - Pair it with a QR code or a 6-digit code (5 minutes, 5 tries). Remove devices at any time.
  - The phone needs no logins: replies and moderation are carried out on the streaming PC.
  - The companion port (4467) only opens once a device is paired or a pairing is in progress.
  - See [docs/COMPANION.md](docs/COMPANION.md).
- **Moderation**:
  - Twitch: delete, timeout (10 minutes, 1 hour or any length up to 14 days), ban and unban.
  - YouTube: remove, 5-minute timeout, hide user.
  - Bans ask first.
- **Twitch through its official API**: **Connect Twitch** in Settings uses Twitch's device sign-in, and the code is pre-filled at twitch.tv/activate.
  - CrossChat asks for three permissions: write chat, delete messages, ban/unban.
  - The token is encrypted for your Windows account (DPAPI). Disconnecting revokes it at Twitch.
  - Once connected, Twitch replies no longer need the browser extension.
- **Quick replies**: one-tap lines and emoji, shared by every device and edited in the app.
- **Answer later**: star messages. A **Questions** view picks out messages that look like questions.
- **Settings dialog**: theme, ding, Twitch connection, paired devices, test alerts for the widgets in OBS.
- The chat app works at phone width with touch: tap a message for its actions.

### Changed

- Every reply and moderation goes through the hub as a job.
  - Twitch is done by the hub itself once connected.
  - YouTube and X are handed to the CrossChat window on the streaming PC, which has the extension.
  - Paired devices see when that window isn't open.
- Paired devices learn within seconds when the CrossChat window on the streaming PC closes.

## [1.0.0] - 2026-10-31

First public release.

### Added

- **Chat window**: Twitch, YouTube, Kick and X chat in one list.
  - Viewer counts per platform and in total.
  - Subs, raids, cheers, Super Chats and memberships marked in the list.
  - Deleted messages and timed-out viewers struck through.
  - Light, dark, or follows Windows.
  - Opens when OBS starts streaming and closes two minutes after it stops.
- **Replies**: type once to post to every live platform, or pick one platform, or answer one person on their own platform. Twitch answers are threaded replies. `?dry` test mode posts nothing.
- **On-stream widgets** as OBS Browser Sources:
  - chat feed;
  - featured message (pick any message in the chat window);
  - viewer counter;
  - alerts for subs, resubs, gifts, raids, cheers, memberships and Super Chats, with an optional chime.
- **Themes**:
  - Theme Studio with a live preview of all four widgets over a chosen backdrop (or your own picture), and test events sent to the sources already in OBS.
  - Eight built-in themes: Classic, Minimal outline, Glass, Bubbles, Compact, Neon, Paper and High contrast.
  - A different theme per scene with `?theme=`.
  - Import and export as JSON.
  - Custom CSS, plus a documented class and variable API (see [docs/THEMES.md](docs/THEMES.md)).
- **X Live**: the browser extension presses Go Live on X Live Studio when OBS starts streaming and ends the X livestream when OBS stops. It also passes X's chat and viewer count to the chat window. There are dry-run and private test modes.
- **OBS script** (`crosschat.lua`):
  - starts the hub with OBS, including portable OBS;
  - buttons for open chat, Theme Studio, hide featured message, go live on X, the X dry run, and restarting the hub;
  - hotkeys for open chat, go live on X and hide featured message.
- **Installer** (`Install.cmd`):
  - finds Python 3.10+ or offers to install it;
  - sets up a private Python environment;
  - asks for your channels;
  - turns on OBS's WebSocket server;
  - adds Start-menu shortcuts.

  Running it again updates CrossChat and keeps your settings and themes. `Uninstall.cmd` removes it and can keep your settings.
- **Security**: the hub answers only on `127.0.0.1` and checks the `Host` header, which blocks DNS rebinding. It refuses actions requested by other websites, and accepts changes only as same-origin JSON. No telemetry.
- **Checks**:
  - 31 Python tests: config, platform parsers, the web server and its access rules, and obs-websocket handling including a wrong password;
  - 15 JavaScript tests for the theme engine;
  - CI on Python 3.10 and 3.14;
  - an end-to-end script that checks 19 things against a portable OBS. All 19 passed on OBS 33.0.1.

### Changed (from the author's private setup this grew out of)

- Every name, channel, path and window position that belonged to one PC is now a setting, and new installs start empty.
- The OBS script finds Python by itself and handles folder names in any language. It finds portable OBS's settings, so CrossChat follows the OBS that started it, never another one that happens to be open.
- The hub ends when its own OBS closes, even while connected.
- Overlays are served by the hub over `http://127.0.0.1`. OBS 33 blocks local-file overlays from reaching the hub.
- Fonts are Windows' own: Segoe UI Variable and Cascadia Mono.

[Unreleased]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.7.2...HEAD
[1.7.2]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.7.1...v1.7.2
[1.7.1]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.7.0...v1.7.1
[1.7.0]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/RandyNorthrup/crosschat-obs/releases/tag/v1.0.0
