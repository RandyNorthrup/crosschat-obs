# Changelog

All notable changes to CrossChat are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/RandyNorthrup/crosschat-obs/releases/tag/v1.0.0
