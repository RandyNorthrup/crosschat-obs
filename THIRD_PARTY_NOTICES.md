# Third-party notices

CrossChat is MIT licensed (see [LICENSE](LICENSE)). It uses the following, under their own licences.

## Included in this repository

| What | Where | Licence |
|---|---|---|
| [Simple Icons](https://simpleicons.org) 16.33.0: Twitch, YouTube, Kick, X, TikTok, Facebook, Instagram and Rumble glyphs | `hub/web/icons.js` | CC0 1.0 |
| [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) 2.0.4 by Kazuhiko Arase, for the pairing QR code | `hub/web/vendor/qrcode.js` | MIT |

The platform names and logos are trademarks of their owners and are used only to show where a chat message came from. CrossChat is not affiliated with or endorsed by OBS Project, X Corp., Twitch, YouTube (Google), Kick, TikTok, Meta (Facebook, Instagram), Rumble or Discord.

## Shipped inside the Windows setup program (`CrossChat-Setup-<version>.exe`)

| What | Licence |
|---|---|
| [Python](https://www.python.org) 3.14 embeddable package (python.org), the Python CrossChat runs on | PSF License Agreement (its licence file ships inside the setup program, next to Python) |
| The Python packages below, the same pinned and checksum-checked versions `Install.cmd` installs | As listed below (their licence files ship with them) |
| [NSIS](https://nsis.sourceforge.io) 3.13, which builds the setup program and its uninstaller | zlib/libpng licence |

## Installed by `Install.cmd` and `Install.command` (downloaded from PyPI, checked against `hub/requirements.lock`)

| Package | Licence |
|---|---|
| [requests](https://github.com/psf/requests) 2.34.2 | Apache-2.0 |
| [websockets](https://github.com/python-websockets/websockets) 16.0 | BSD-3-Clause |
| [urllib3](https://github.com/urllib3/urllib3) 2.8.0 (requests) | MIT |
| [idna](https://github.com/kjd/idna) 3.20 (requests) | BSD-3-Clause |
| [charset-normalizer](https://github.com/jawah/charset_normalizer) 3.5.2 (requests) | MIT |
| [certifi](https://github.com/certifi/python-certifi) 2026.10.23 (requests) | MPL-2.0 |

## Loaded at run time only when a theme asks for it

| What | Licence |
|---|---|
| Fonts from [Google Fonts](https://fonts.google.com) named by a theme (the built-in Bubbles theme uses Nunito) | SIL Open Font License 1.1 |
| Twitch emote images, from Twitch's CDN as they appear in chat | Twitch's terms |
