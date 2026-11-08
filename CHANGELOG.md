# Changelog

All notable changes to CrossChat are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.9.0] - 2026-11-08

### Highlights

- **Your own logos and names on stream**, or none at all: one button hides which platform a message came from.
- **Streamlabs Desktop**, and a **Start stream** button for any other streaming app. CrossChat no longer needs OBS.
- **A [wiki](https://github.com/RandyNorthrup/crosschat-obs/wiki)** with step-by-step guides.

### Added

- **Your own platform logos and names on the on-stream widgets.** In the Theme Studio: one logo or name for every platform, one per platform (which wins), the plain bubble, or no name. **Hide every platform** removes the logos, names and platform colours; alert wording such as "sent a Super Chat" stays until you change it. Logos are kept inside the theme, so they export with it. See [docs/THEMES.md](docs/THEMES.md#your-own-logos-and-names).
- **Streamlabs Desktop.** CrossChat follows its stream with no token and nothing to set up there, and closes when it closes. Tested on Windows with Streamlabs Desktop 1.21.9, signed out: a real stream to a private receiver from start to stop, with all four widgets and custom logos in the video it sent. See [Known limits](README.md#known-limits).
- **Any other streaming app.** A **Start stream** / **End stream** button in the chat window, or `control.py stream-start` and `stream-end`. See [Other streaming apps](README.md#other-streaming-apps). Tested on Windows with vMix 29, XSplit Broadcaster 4.6 and Meld Studio 0.10: the widgets in each app, and the button in the chat window of an installed CrossChat.
- **Settings → Streaming app** (`"broadcaster"` in `config.json`), and **Close CrossChat** (or `control.py leave`) when it follows Streamlabs or nothing.
- `PRIVACY.md`: CrossChat's privacy policy.

### Changed

- A theme file can now be up to 224 KB (it was 64 KB), to hold its logos.
- CrossChat's own words no longer assume OBS: **Copy address**, **Send test** and **Add to your stream** in the Theme Studio, and the hints in Settings.
- The chat window now asks you to reload the extension only when it's too old to work with this CrossChat, not after every update.
- The extension's description is shorter.
- The hub's made-up test events and its demo cover all eight platforms.
- A chat box no longer stops at 500 characters: a message too long for a platform shows the red "too long" text instead.
- A window that stops reporting is noted after 90 seconds, not 20, because a browser slows the timers of a page that is covered.
- The Mac and Linux installers ask about Instagram and the update notice too.
- The Theme Studio button and links in the OBS script follow the `port` setting.

### Fixed

- **`overlay.platforms` in `config.json` did nothing.** The chat widget now honours it, after `?platforms=` and a theme's own list.
- A broken `config.json` is now shown to you and written to the log, instead of quietly falling back to defaults.
- When another program holds CrossChat's port, CrossChat says so once. A second copy of CrossChat still leaves quietly.
- A full disk or an unwritable chat history no longer stops chat from coming in or a stream from starting: you get one warning and that stream isn't saved.
- Opening Chat history no longer freezes live chat and the widgets.
- Platform windows now close when OBS closes, not only the chat window.
- A damaged `filters.json`, `tts.json`, `quick.json` or `devices.json` is kept as `<name>.bad` with a warning, rather than silently reset. A bad `filters.json` used to switch filtering off.
- A sign-in that can't be read (a locked keyring, say) shows as an error in Settings instead of "Not connected".
- YouTube picks **Live chat** by name and tells you if it had to fall back to Top chat.
- Facebook and Instagram could lose lines when many arrived at once. Lines are now sent in batches the hub reads whole.
- The chat window could hide its own errors while drawing a message. They now reach the console, and a lost connection shows *reconnecting…*.
- OBS shows a message if Python can't start or the hub keeps stopping, instead of only writing it to the Script Log.
- **Start the hub again** in OBS no longer loses track of the hub already running.
- Uninstalling on a Mac or Linux keeps your quick replies, filters and read-aloud settings, as Windows does. Every uninstaller asks about your chat history (a silent uninstall removes it), and reports it if the folder couldn't be removed.
- The Tailscale switch no longer appears on a Mac, where it can't work.
- A single gift on Rumble now reads *a sub*.

### Security

- The end-to-end test no longer writes a fixed WebSocket password into its throwaway OBS profile. OBS makes up its own, as on a fresh install, and the test reads it from OBS's settings. CrossChat itself isn't affected.

## [1.8.0] - 2026-11-01

### Highlights

- **Signed Windows installer.** Since 1.7.2, `CrossChat-Setup-<version>.exe` is code-signed by Randy Northrup (Azure Artifact Signing), and the release workflow checks the signature before publishing.
- **Linux.** A new download, tested with real OBS on Ubuntu 25.10 and, on every change, on Ubuntu 24.04 (OBS from the OBS Project's PPA and from Flathub).
- **Mac, out of beta.** Tested with real OBS 33.0.1 on Intel Macs (macOS 15.7) and, on every change, on an Apple-silicon Mac (macOS 26).
- **Moderation tested live, with a second account in the chat** (31 October 2026):
  - Twitch: delete, timeout, ban and unban, also from the CrossChat dock inside OBS.
  - YouTube: remove, 5-minute timeout and hide user; remove also from the dock.
  - Kick: delete, timeout, ban and unban; timeout also from the dock.
  - Facebook: delete a comment.
  - Rumble: delete was tested on the streamer's own message in a real live; moderating another viewer isn't tested yet.
- **Found and fixed by those live tests:** YouTube moderation, Kick chat (it had stopped arriving) and Facebook comments (viewers' comments never reached CrossChat).
- **Real OBS end to end on Windows, Mac and Linux on every change**, plus CrossChat's windows placed and closed by its extension on every system.

### Added

- `docs/COMPARISON.md`: CrossChat next to Restream, Streamlabs, StreamElements, Social Stream Ninja, Casterlabs and Streamer.bot, each claim linked to that product's own page (checked 31 October to 1 November 2026).
- **Linux:** a Linux download, `CrossChat-<version>-linux.tar.gz`, installed with `bash scripts/install.sh` into `~/.local/share/CrossChat` (readable by your account only), with app-menu entries and an uninstaller. Checked on Ubuntu 25.10 with Ubuntu's OBS 30.2.3 and OBS 33.0.1 from Flathub, and on every change on Ubuntu 24.04 with OBS 32.2.0 from the OBS Project's PPA and 33.0.1 from Flathub (see the README's Linux section for exactly what, and what isn't checked yet).
  - **Read-aloud** uses the computer's own voices through speech-dispatcher. Google Chrome offers them only when it's started with `--enable-speech-dispatcher` (without it, only Google's online voices, which CrossChat doesn't pick by itself). The installer says whether speech-dispatcher is there, and which packages add it.
  - **Sign-ins** are encrypted as on a Mac (AES-256 and HMAC-SHA256) under a key kept in your desktop keyring (Secret Service: GNOME Keyring, KWallet and others), through `secret-tool`, which gets the key on its standard input, never on a command line. **With no keyring, CrossChat keeps no sign-ins at all and says why**: Twitch and Kick drop a sign-in they couldn't encrypt, and Rumble and Discord say the keyring's reason instead of "Could not save it".
  - **OBS from Flathub** works: the OBS script starts the hub outside OBS's sandbox with `flatpak-spawn`, and the hub leaves when OBS does. The installer finds Ubuntu's (or any) `obs` and OBS from Flathub, switches on their WebSocket servers, and says when an OBS has no Browser Source (Ubuntu's and Debian's own package leaves it out, so the widgets need OBS from Flathub or the OBS Project's PPA).
  - **The chat window** opens in Chrome, Edge, Chromium or Brave, and the extension places, moves and closes it (see below), on X11 and on Wayland, where the desktop chooses the place and the extension sets the size. Without the extension it's done through X11, which on Wayland reaches the browser only when it runs through XWayland; otherwise the window opens where the desktop puts it, and "Open chat" doesn't open a second one.
  - **Tailscale** for the companion away from home: only the address of Tailscale's own `tailscale0` interface counts, while it's up.
  - The real-OBS check (`scripts/obs_e2e.py`) runs on Linux with the installed `obs` (settings in a throwaway folder) or `--obs flatpak`, on an Xvfb display of its own when there's no desktop. On every change, GitHub's Ubuntu machines run the tests with a real keyring, real browser windows, an install and uninstall from the download, and OBS end to end from the OBS Project's PPA and from Flathub.
- The real-OBS check also starts OBS again 3 seconds after closing it, and checks its WebSocket server works and its script starts the hub again (every system).
- **The CrossChat extension places, moves and closes CrossChat's own windows**: the chat window, and the X, TikTok, Facebook, Instagram and Rumble pages it opens. It uses the browser's own window API, which needs no permission (the extension still asks for none), and touches only windows CrossChat opened: a bare `--app` window with one tab at that window's own address, and for a page, the window CrossChat recorded or a new one at the exact address it opened. It never moves or closes a browser window of yours, even one with the chat open in a tab (SECURITY.md has the rules). The jobs come from the hub through the CrossChat window only, like replies. The system's own way stays for when the extension isn't there or can't. Reload the extension in `chrome://extensions` after updating.
  - **macOS:** it's the way that works when OBS starts the hub (macOS refuses AppleScript to programs OBS starts). Checked on macOS 15.7.4 (Intel Mac mini) with Chrome 156: the chat window and a page placed, the chat window moved by Open chat, both closed after the stream, with the Mac's own window server showing each window exactly there; and the same with OBS 33.0.1 starting the hub, which then left once OBS quit.
  - **Linux:** checked on Ubuntu 25.10 with Chrome 153 on an X11 display (Xvfb), through KWin 6.4.5's XWayland (the X server showing each window exactly there), and on Wayland (KWin on a virtual screen, the browser as a Wayland program), where KWin chooses where a window goes (Wayland lets no program place one) and the extension sets its size (exactly, says KWin) and closes it. All at a display scale of 100 %.
  - **Windows:** Windows' own way still places a window it can see, because the browser's window API counts Windows' invisible resize borders in: asked for 200,150 420x560, a browser window's visible frame was 207,150 406x553 on GitHub's Windows machines, while Windows' way puts the visible edges exactly in place. The extension closes the windows there, and places one Windows can't see; that part hasn't run on a real Windows desktop yet.
  - A running browser opens a new window where it likes: Chrome takes `--window-position` and `--window-size` only when it starts with that window (in the checks, every new window opened over the first one on macOS and Linux, and on Windows one asked for at 100,100 600x500 opened at 10,10 1004x700). So a chat window CrossChat opened is placed once it connects, and a page as soon as it shows. A window the desktop sizes again just after it opened (KWin on Wayland), or keeps maximized one way (KWin through XWayland, with a window that opened as tall as the screen), is placed again.
  - `scripts/window_e2e.py` is the real check: Chrome with a throwaway profile and the checkout's extension loaded over DevTools, the hub with a stand-in for OBS (or, on a Mac, OBS itself), decoy windows that must stay put, and where the desktop itself has the windows. The new `window-control` job runs it on every change on GitHub's Ubuntu and macOS machines.
- **Real OBS on Windows, on every change.** The checks workflow's new `obs-windows` job runs `scripts/obs_e2e.py` with the portable OBS 33.0.1 from the OBS Project's release and ffmpeg 9.0.2 from gyan.dev, each download checked against the SHA-256 its maker publishes: all 27 checks pass on GitHub's Windows Server 2025, the three restart checks included. All three systems now run the same real-OBS check.

### Fixed

- **A new window was looked for for 10 seconds only.** A browser starting cold took 10 s to show its first window on GitHub's Ubuntu machines, where the real-window test failed once; such a window was left where the browser put it and wasn't closed after the stream. CrossChat now looks for up to 30 s, on every system.
- **Windows opening together could be taken for each other.** TikTok's, Facebook's and Instagram's pages open together when the stream starts, and the system's way knows a new window by its not having been there before. They now open one at a time.
- **The hub stayed after OBS closed while a chat page was still open** (the chat in a tab, or a chat window it couldn't close, as on a Mac), keeping its port: from Python 3.12.1, leaving the hub's server waits for every open connection, and a chat page's live feed never ends by itself. The hub now stops listening without waiting. Found while checking the windows; checked with OBS 33.0.1 on a Mac with the chat open in a tab.
- Facebook comments showed in CrossChat with a stray "·" in front (the separator Facebook puts after the commenter's name).
- **Click here to retry in the CrossChat dock in OBS** showed "not from another website" instead of the chat. When the dock loads before CrossChat answers, OBS shows its own error page, which has an origin of its own, so the hub took the retry for another website opening the chat window. The hub now opens the chat window for a click on a link to it in OBS's own browser (its User-Agent says `OBS/`); anything else from another site is still refused (see SECURITY.md). Found with OBS 33.0.1 from Flathub on Linux, where the dock loaded before CrossChat answered in most starts.
- **The real-OBS check's docked chat window was hidden on every system.** The check wrote the dock into OBS's settings without a window layout, so OBS's first start ran Docks → Reset UI, which leaves Custom Browser Docks floating and hidden; the dock's page still loaded out of sight, so the check passed (on Linux it was skipped: the hidden dock often showed only OBS's error page). It now gives OBS a layout with the dock docked on the right, checks the layout OBS saves as it closes (it said "hidden, floating" before, on Windows, macOS and Linux), and presses Click here to retry when the dock opened too early. It runs on Linux too now.

- **Linux:** the OBS script hands the hub only standard input, output and error. Without that, posix_spawn passes every file and socket OBS has open, as on a Mac (see below); on Linux it's closed with one file action (glibc 2.34 and newer), or one per open file on older systems.
- The tests no longer close a real CrossChat window on the computer running them (the hub closes its chat window when OBS goes away, and some tests make OBS go away).

- **Mac:** the hub no longer gets a copy of everything OBS has open. The OBS script started it with all of OBS's files and sockets, OBS's WebSocket server among them, so after OBS closed the hub kept OBS's WebSocket port taken (about 20 seconds in our tests), and an OBS opened again in that time couldn't start its WebSocket server (CrossChat then couldn't follow it). Found with OBS 33.0.1 on macOS 15.
- **Mac:** the chat window's notice said "Start menu → CrossChat → Open chat"; on a Mac it now names Applications → CrossChat in the home folder. The Paired-devices hint about Windows' network question no longer shows on a Mac, and the Theme Studio's look button says "follows this device", not "follows Windows".
- The chat window styled a first-time chatter's **1ST** flag and line like the Settings "Set up your channels" note (a padded, bordered box), so the flag stood out of the line as a large pill and stretched the **Q** flag beside it. Seen in OBS's dock on a Mac; the same on Windows.
- **Mac:** the README said macOS asks whether OBS may control your browser, so that CrossChat can move and close the chat window. It doesn't ask: macOS refuses Apple Events from programs OBS starts, because OBS 33 is signed without the entitlement for them (its log says `kTCCServiceAppleEvents requires entitlement com.apple.security.automation.apple-events but it is missing`). The README now says CrossChat can't move or close the chat window on a Mac; the window still opens where it should.
- **Mac:** the README and the installer say where the Applications → CrossChat folder is (the Applications folder in your home folder, not Finder's main one), and that `Install.command` has to be started from Terminal: macOS 15 refuses to open it with a double-click, because the download isn't signed by Apple.
- **Kick chat stopped arriving.** Kick changed the key of its public chat feed, and Kick's server refused the one CrossChat had built in ("App key ... not in this cluster"), so Kick chat kept reconnecting and showed nothing. CrossChat now asks Kick for the current key the way Kick's own web chat does (signed out, with a random id), and falls back to the new one. When Kick's feed refuses a connection, the log says why.
- **YouTube moderation clicked the wrong button.** YouTube now shows a top fan's "#1" rank inside the chat line, before the message's own menu, and CrossChat clicked that rank (opening the Top fans list) instead of the menu, so remove, timeout and hide user all failed with "YouTube did not offer that here". The extension now opens only the message's "Chat actions" menu. Reload the extension in `chrome://extensions` after updating.
- **YouTube moderation still couldn't work from the CrossChat window.** YouTube offers the channel owner Remove, timeout and Hide user only on its own chat page; the chat embedded in the CrossChat window shows just "Go to channel" and "Pin message". The extension now moderates in YouTube's chat pop-out for the live, which it opens in a background tab of the browser (never in front; a minimized window only when no browser window is open). It keeps that one tab for the whole live, closes one left from an earlier live, reloads it if the extension was reloaded since, and the tab closes itself once the live is over or CrossChat has been unreachable twice in a row (half a minute apart). A pop-out you opened yourself is used but never closed.
- **YouTube timeouts weren't confirmed.** YouTube now asks for the length in a "Timeout duration" dialog; CrossChat picks the length nearest the one asked for (5 minutes from the menu) and only reports the timeout done once Confirm has closed the dialog. The menu says "Timeout 5 minutes", and the window and the hub wait up to 75 seconds for a YouTube job, since the pop-out may have to load first.
- **Facebook comments stopped reaching CrossChat.** Live Producer now puts a hidden avatar link to the comment before the commenter's name, so the name was read as empty and the comment was dropped. The name now comes from the first comment link with text.

### Changed

- **Linux is no longer a beta.** On Ubuntu 25.10, on a virtual X11 display with Google Chrome 153: the OBS script and the hub following Ubuntu's OBS 30.2.3 and OBS 33.0.1 from Flathub, the widgets and the chat docked in OBS (Flathub), the installer and uninstaller, the desktop keyring, the extension (the chat window posts a test reply through it), read-aloud with speech-dispatcher's voices, and the phone companion (paired from a Windows PC, refused before pairing, with a wrong code, from another website and once removed). On every change, on Ubuntu 24.04, with OBS from the OBS Project's PPA and from Flathub. Not seen yet: a Linux desktop someone sits at, other distributions, and browsers other than Google Chrome. The README's Linux section lists exactly what.
- **The Mac version is no longer a beta.** CrossChat 1.7.1 and this version were run with OBS 33.0.1 on macOS 15.7.4 (Intel Mac mini) and 15.7.9 (Intel MacBook Pro): download and checksum, installer, the OBS script and the hub following OBS, the four widgets and the chat docked inside OBS, the login Keychain, the extension in Chrome 156, read-aloud with the Mac's voices, the phone companion (paired from a Windows PC and from the MacBook's Chrome), and the uninstaller. The README's Mac section lists exactly what.
- **Real OBS on an Apple-silicon Mac, on every change.** The checks workflow's new `obs-mac` job installs OBS and ffmpeg from Homebrew on GitHub's Apple-silicon Mac (macOS 26), installs CrossChat from the Mac download and runs `scripts/obs_e2e.py` against that OBS: all 24 checks pass with OBS 33.0.1. It can also be started by hand.
- The real-OBS check (`scripts/obs_e2e.py`) runs on a Mac too, with the installed OBS.app and a stand-in home folder, so your own OBS settings are never touched. It also checks that OBS's own browser shows the four widgets and the docked chat (with test chat in it), and that OBS's WebSocket port is free once OBS closes. `--crosschat` tests an installed copy, `--ffmpeg` names the RTMP receiver, and the logs are kept when something fails.
- The hub's start line in `crosschat.log` names the Python running it.
- The README says what to do when the CrossChat dock in OBS says "Couldn't load that page!" (OBS opened it before CrossChat was ready: press "Click here to retry"), and that OBS on a Mac needs the Input Monitoring permission for hotkeys while another app is in front.
- README's Known limits say what moderation was checked live on 31 October 2026, with a second account in the chat, on both sides (the viewer's and the streamer's):
  - Twitch delete, timeout, ban and unban work, from the CrossChat window in Chrome; timeout and unban also from the CrossChat dock inside OBS.
  - YouTube remove, 5-minute timeout and hide user work from the CrossChat window (with the fixes above, in an unlisted live), and remove from the CrossChat dock inside OBS. In 1.7.1 all three had failed. The pop-out tab closed itself after CrossChat was closed.
  - Kick delete, timeout, ban and unban work from the CrossChat window, and timeout from the CrossChat dock inside OBS.
  - Facebook: deleting another commenter's comment (a Facebook Page's, on a short public test live) works from the CrossChat window.
  - Rumble moderation of a viewer still hasn't been seen working: Rumble's sign-up for a test account stopped at Cloudflare's "Verify you are human" check ("Verification failed").
  - A reply typed once in the CrossChat window reached Twitch, YouTube and Kick chat.

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

[Unreleased]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.9.0...HEAD
[1.9.0]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.8.0...v1.9.0
[1.8.0]: https://github.com/RandyNorthrup/crosschat-obs/compare/v1.7.2...v1.8.0
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
