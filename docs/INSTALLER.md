# The CrossChat setup program

`CrossChat-Setup-<version>.exe` is the normal way to install CrossChat. The zip with `Install.cmd` is still published for anyone who prefers it.

## What it does

- Installs CrossChat for **your Windows account only**, in `%LOCALAPPDATA%\CrossChat`. It needs no administrator rights.
- Brings its own Python: python.org's **Windows embeddable package**, with CrossChat's few packages already in it. Nothing else has to be installed, and it doesn't touch any other Python on the PC.
- On a first install, writes a default `config.json`. You set your channels in CrossChat's **Settings**.
- If OBS's WebSocket server is off and OBS is closed, asks whether to switch it on. CrossChat follows your stream through it. If OBS is open, it tells you where to switch it on instead.
- Adds a **CrossChat** folder to the Start menu: Open chat, Try the demo, Theme Studio, Go live on X, Test X, Hide featured message, CrossChat folder, First steps, Uninstall.
- Registers CrossChat in **Settings → Apps → Installed apps**, under your account (`HKCU`).
- Puts the OBS script's path on your clipboard, and offers to open CrossChat and a "first steps" page at the end.

**Updating** is running the newer setup program. It keeps everything that's yours:

- `config.json`, `themes\`, `quick.json`, `filters.json`, `tts.json`;
- the sign-ins `twitch.bin`, `kick.bin` and `rumble.bin`, and the Discord webhook `discord.bin`;
- `logs\`, your chat history.

If OBS is open with CrossChat running, setup stops CrossChat, replaces its files and starts it again for that OBS.

Then reload the extension: `chrome://extensions` (or `edge://extensions`) → the reload arrow on CrossChat. The browser keeps running the old extension until then, and the chat window shows a notice while it does.

## Uninstalling

Start menu → CrossChat → **Uninstall CrossChat**, or Settings → Apps → CrossChat → Uninstall. It stops CrossChat, offers to keep your settings and themes in `Documents\CrossChat backup`, and removes the folder, the Start-menu entries and the Apps entry.

Two things only you can remove: the script in OBS (*Tools → Scripts*, select it, **−**), and the extension in your browser.

## Silent install, for scripts

```powershell
.\CrossChat-Setup-1.7.1.exe /S                        # installs; switches on OBS's WebSocket server if it's off
& "$env:LOCALAPPDATA\CrossChat\uninstall.exe" /S       # removes; keeps settings and themes in Documents\CrossChat backup
```

## Checking a download

Each setup program comes with a `.sha256` file and a signed build provenance attestation:

```powershell
gh attestation verify CrossChat-Setup-1.6.0.exe --repo RandyNorthrup/crosschat-obs
```

The setup program isn't code-signed yet, so Windows may say "Windows protected your PC". Choose **More info → Run anyway**. CrossChat has applied to [SignPath Foundation](https://signpath.org) for free code signing (see the README's code signing policy). The bundled `python.exe` and `pythonw.exe` are signed by the Python Software Foundation.

## How it's built

`installer/build.ps1` runs in the release workflow and makes the setup program from the repository:

1. Copies CrossChat's files as they are installed.
2. Downloads python.org's embeddable Python and checks it against the SHA-256 published on python.org's release page.
3. Fetches CrossChat's packages with pip into the bundle only (`--target`). It uses the exact versions and SHA-256 hashes in `hub/requirements.lock`, wheels only.
4. Checks that the bundled Python can run CrossChat.
5. Downloads NSIS 3.13 and checks it against its pinned SHA-256 and SourceForge's published MD5. Then builds `installer/crosschat.nsi`.

Nothing is installed on the build machine. To build it yourself on Windows: `pwsh installer/build.ps1`. The result is `dist\CrossChat-Setup-<version>.exe`.
