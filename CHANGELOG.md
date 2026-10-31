# Changelog

All notable changes to CrossChat are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/RandyNorthrup/crosschat-obs/releases/tag/v1.0.0
