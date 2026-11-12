#!/bin/bash
# CrossChat installer for macOS and Linux. On a Mac, run Install.command (it starts this), or:
# bash scripts/install.sh. On Linux, open a terminal in the unpacked folder and run: bash scripts/install.sh
# Safe to run again: it updates CrossChat and keeps your settings and themes.
#
#   --quiet   ask nothing: keep the existing settings, or start from the defaults
set -eo pipefail

QUIET=0
if [ "${1:-}" = "--quiet" ]; then QUIET=1; fi

SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
LINUX=0
if [ "$(uname -s)" = Linux ]; then LINUX=1; fi
if [ "$LINUX" = 1 ]; then
    # the XDG folders (only when they are full paths, as the standard says)
    DATA="${XDG_DATA_HOME:-}"
    case "$DATA" in /*) ;; *) DATA="$HOME/.local/share" ;; esac
    CONFIG_HOME="${XDG_CONFIG_HOME:-}"
    case "$CONFIG_HOME" in /*) ;; *) CONFIG_HOME="$HOME/.config" ;; esac
    APP="$DATA/CrossChat"
    SHORTCUTS="$DATA/applications"          # the desktop's app menu: crosschat-*.desktop
    FLATPAK_OBS="$HOME/.var/app/com.obsproject.Studio/config/obs-studio"
    SYSTEM='Linux'
    MACHINE='computer'
else
    APP="$HOME/Library/Application Support/CrossChat"
    SHORTCUTS="$HOME/Applications/CrossChat"
    SYSTEM='macOS'
    MACHINE='Mac'
fi
VERSION="$(sed -n 's/^VERSION = "\(.*\)"$/\1/p' "$SOURCE/hub/hub.py")"

say() { printf '%s\n' "$1"; }
step() { printf '\n\033[36m== %s\033[0m\n' "$1"; }
note() { printf '\033[33m%s\033[0m\n' "$1"; }
fail() { printf '\033[31m%s\033[0m\n' "$1"; exit 1; }
ask() {          # ask QUESTION [DEFAULT]: the answer, or DEFAULT when it's left empty (or with --quiet)
    local question="$1" default="${2:-}" answer=""
    if [ "$QUIET" = 1 ]; then printf '%s' "$default"; return 0; fi
    if [ -n "$default" ]; then question="$question [$default]"; fi
    read -r -p "$question: " answer </dev/tty || answer=""
    answer="$(printf '%s' "$answer" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    printf '%s' "${answer:-$default}"
}
confirm() {      # confirm QUESTION [y|n]: success for yes
    local answer
    answer="$(ask "$1 (y/n)" "${2:-y}")"
    case "$answer" in [yY]*) return 0 ;; *) return 1 ;; esac
}
applescript_text() {   # a value made safe inside an AppleScript "string"
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}
desktop_arg() {        # a value made safe as one argument on a .desktop file's Exec line (and % kept literal)
    printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\\\\\/g; s/"/\\\\"/g; s/`/\\\\`/g; s/\$/\\\\$/g; s/%/%%/g')"
}

# A Python 3.10 or newer: its full path, or nothing. Apple's /usr/bin/python3 counts only when the developer tools are
# there (otherwise just asking it makes macOS offer to install them).
find_python() {
    local candidate found
    for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 /opt/homebrew/bin/python3 /usr/local/bin/python3 \
                     /Library/Frameworks/Python.framework/Versions/Current/bin/python3 python3; do
        found="$(command -v "$candidate" 2>/dev/null || true)"
        [ -n "$found" ] || continue
        if [ "$LINUX" != 1 ] && [ "$found" = /usr/bin/python3 ] && ! xcode-select -p >/dev/null 2>&1; then continue; fi
        if "$found" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
            printf '%s' "$found"
            return 0
        fi
    done
    return 1
}

printf '\n  CrossChat %s installer for %s\n' "$VERSION" "$SYSTEM"
say '  Every stream chat in one window, on-stream chat widgets, and X Live started with OBS.'
say "  Installs to $APP"

# ---- Python -----------------------------------------------------------------------------------------------
step 'Python'
PYTHON="$(find_python || true)"
if [ -z "$PYTHON" ] && [ "$LINUX" = 1 ]; then
    note 'CrossChat needs Python 3.10 or newer, and this computer has none.'
    say 'Install it with your package manager, for example:'
    say '  Ubuntu, Debian: sudo apt install python3 python3-venv'
    say '  Fedora: sudo dnf install python3      Arch: sudo pacman -S python'
    fail 'Then run bash scripts/install.sh again.'
elif [ -z "$PYTHON" ]; then
    note 'CrossChat needs Python 3.10 or newer, and this Mac has none.'
    say 'Install it from https://www.python.org/downloads/macos/ (the "macOS 64-bit universal2 installer"),'
    say 'or with Homebrew (https://brew.sh): brew install python@3.13'
    fail 'Then run Install.command again.'
fi
say "Python $("$PYTHON" -c 'import platform; print(platform.python_version())') found ($PYTHON)."

# ---- files ------------------------------------------------------------------------------------------------
step 'Copying CrossChat'
# OBS starts the hub as .../CrossChat/obs/../hub/hub.py, so match the folder and the file separately.
restart_for=""
while IFS= read -r line; do
    pid="${line%% *}"
    command="${line#* }"
    case "$command" in *"$APP/"*hub.py*) ;; *) continue ;; esac
    case "$command" in *--demo*) continue ;; esac
    say 'Stopping the running CrossChat hub (it starts again at the end).'
    case "$command" in *--obs-pid*) restart_for="$command" ;; esac
    kill "$pid" 2>/dev/null || true
done < <(ps -axo pid=,command= | sed 's/^ *//')
mkdir -p "$APP"
if [ "$LINUX" = 1 ]; then
    chmod 700 "$APP"            # your settings, chat history and encrypted sign-ins: for your account only
fi
for folder in extension hub obs; do
    if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete --exclude '__pycache__' "$SOURCE/$folder/" "$APP/$folder/" || fail "Copying $folder failed."
    else                        # (some Linux systems come without rsync)
        rm -rf "${APP:?}/$folder" && cp -R "$SOURCE/$folder" "$APP/$folder" && rm -rf "$APP/$folder/__pycache__" || fail "Copying $folder failed."
    fi
done
for file in config.example.json README.md CHANGELOG.md LICENSE THIRD_PARTY_NOTICES.md Uninstall.command; do
    if [ "$LINUX" = 1 ] && [ "$file" = Uninstall.command ]; then continue; fi
    if [ -f "$SOURCE/$file" ]; then cp -f "$SOURCE/$file" "$APP/"; fi
done
mkdir -p "$APP/scripts"
cp -f "$SOURCE/scripts/uninstall.sh" "$APP/scripts/"
chmod +x "$APP/Uninstall.command" "$APP/scripts/uninstall.sh" 2>/dev/null || true
if [ "$LINUX" != 1 ]; then
    xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true      # the download's "from the internet" mark
fi
say 'Done.'

# ---- private Python environment ---------------------------------------------------------------------------
step "Setting up CrossChat's Python packages"
VENV_PY="$APP/.venv/bin/python3"
if ! "$VENV_PY" -c 'import sys' >/dev/null 2>&1; then
    if ! "$PYTHON" -m venv --clear "$APP/.venv"; then
        if [ "$LINUX" = 1 ]; then
            note "Python's venv module is missing. On Ubuntu and Debian: sudo apt install python3-venv"
        fi
        fail 'Could not create the Python environment.'
    fi
fi
# exact versions with their checksums: pip refuses anything that doesn't match what was tested
"$VENV_PY" -m pip install --disable-pip-version-check --no-warn-script-location -q --require-hashes -r "$APP/hub/requirements.lock" ||
    fail 'Installing the Python packages failed (see above). Check the internet connection and run the installer again.'
say 'Done.'

# ---- Linux: where sign-ins are kept -------------------------------------------------------------------------
if [ "$LINUX" = 1 ]; then
    step 'Keyring'
    if command -v secret-tool >/dev/null 2>&1; then
        say 'Sign-ins (Twitch, Kick, Rumble, Discord) are kept encrypted, under a key in your desktop keyring.'
    else
        note 'Sign-ins (Twitch, Kick, Rumble, Discord) are kept under a key in your desktop keyring, through secret-tool,'
        note 'which is not installed. Everything else works without it; CrossChat just keeps no sign-ins. To add it:'
        say '  Ubuntu, Debian: sudo apt install libsecret-tools    Fedora: sudo dnf install libsecret    Arch: sudo pacman -S libsecret'
    fi
    step 'Read-aloud'
    if command -v speech-dispatcher >/dev/null 2>&1; then
        say "Chat is read aloud with this computer's own voices (speech-dispatcher)."
    else
        note "Reading chat aloud uses this computer's own voices, through speech-dispatcher, which is not installed."
        note 'Everything else works without it. To add it:'
        say '  Ubuntu, Debian: sudo apt install speech-dispatcher speech-dispatcher-espeak-ng'
    fi
    say 'Google Chrome offers those voices only when it is started with --enable-speech-dispatcher.'
fi

# ---- privacy ----------------------------------------------------------------------------------------------
step 'Privacy'
say "CrossChat runs only on this $MACHINE. It has no server, no account and no telemetry."
say 'It connects only to the chat platforms you set up, and, unless you turn them off, to 7TV, BetterTTV and'
say "FrankerFaceZ for emote pictures (they get your Twitch channel's public id). If you want it, it also asks GitHub"
say 'once a day whether a newer CrossChat is out (off unless you say yes below).'
say 'Every connection and what it sends: https://github.com/RandyNorthrup/crosschat-obs/blob/main/SECURITY.md#what-leaves-your-pc'

# ---- your channels ----------------------------------------------------------------------------------------
step 'Your channels'
CONFIG="$APP/config.json"
if [ -f "$CONFIG" ]; then
    say "Keeping your settings in $CONFIG"
else
    say 'Which channels does your stream go to? Paste a name or a link; leave empty to skip.'
    CROSSCHAT_TWITCH="$(ask 'Twitch channel')"
    CROSSCHAT_YOUTUBE="$(ask 'YouTube channel (@handle or link)')"
    CROSSCHAT_KICK="$(ask 'Kick channel')"
    CROSSCHAT_TIKTOK="$(ask 'TikTok @name (if you go LIVE on TikTok)')"
    if confirm 'Do you go live on Facebook?' n; then CROSSCHAT_FACEBOOK=1; else CROSSCHAT_FACEBOOK=0; fi
    if confirm 'Do you go live on Instagram from OBS (Create, then Live video, on instagram.com)?' n; then CROSSCHAT_INSTAGRAM=1; else CROSSCHAT_INSTAGRAM=0; fi
    if confirm 'Do you stream to X (it needs X Premium and Live Studio)?' n; then CROSSCHAT_X=1; else CROSSCHAT_X=0; fi
    if confirm "Show 7TV, BetterTTV and FrankerFaceZ emotes (asks those services for your channel's emotes)?"; then
        CROSSCHAT_EMOTES=1
    else
        CROSSCHAT_EMOTES=0
    fi
    if confirm 'Tell you when a new CrossChat is out (asks GitHub once a day; sends nothing about you, downloads nothing)?' n; then
        CROSSCHAT_UPDATES=1
    else
        CROSSCHAT_UPDATES=0
    fi
    CROSSCHAT_X_AUTO="" CROSSCHAT_X_SOURCE="" CROSSCHAT_X_TITLE=""
    if [ "$CROSSCHAT_X" = 1 ]; then
        if confirm 'Go live on X by itself whenever OBS starts streaming?'; then CROSSCHAT_X_AUTO=1; else CROSSCHAT_X_AUTO=0; fi
        CROSSCHAT_X_SOURCE="$(ask 'Name of the source in X Live Studio that OBS streams to' 'OBS')"
        CROSSCHAT_X_TITLE="$(ask 'Title for your X livestreams' 'Live now')"
    fi
    export CROSSCHAT_TWITCH CROSSCHAT_YOUTUBE CROSSCHAT_KICK CROSSCHAT_TIKTOK CROSSCHAT_FACEBOOK CROSSCHAT_INSTAGRAM CROSSCHAT_X \
           CROSSCHAT_EMOTES CROSSCHAT_UPDATES CROSSCHAT_X_AUTO CROSSCHAT_X_SOURCE CROSSCHAT_X_TITLE
    "$VENV_PY" "$APP/hub/setup_config.py" config "$APP/config.example.json" "$CONFIG" || fail 'Could not write config.json.'
    say "Saved to $CONFIG (edit it any time; restart OBS afterwards)."
fi

# ---- OBS ----------------------------------------------------------------------------------------------------
step 'OBS Studio'
websocket_step() {     # websocket_step CONFIG.JSON: that OBS's WebSocket server is on, or how to switch it on
    local ws="$1" ws_on=0
    if [ -f "$ws" ] && "$VENV_PY" -c 'import json, sys; sys.exit(0 if json.load(open(sys.argv[1], encoding="utf-8-sig")).get("server_enabled") else 1)' \
            "$ws" 2>/dev/null; then
        ws_on=1
    fi
    if [ "$ws_on" = 1 ]; then
        say "OBS's WebSocket server is on. CrossChat reads its port and password from OBS by itself."
    elif [ "$obs_running" = 1 ]; then
        note "OBS's WebSocket server is off. In OBS: Tools > WebSocket Server Settings > tick \"Enable WebSocket server\" > OK."
    elif confirm 'CrossChat follows OBS through its WebSocket server, which is off. Turn it on now?'; then
        "$VENV_PY" "$APP/hub/setup_config.py" websocket "$ws"
        say 'Turned on (with a password; CrossChat reads it from OBS).'
    else
        note 'Later, in OBS: Tools > WebSocket Server Settings > tick "Enable WebSocket server".'
    fi
}
obs_running=0
if [ "$LINUX" = 1 ]; then
    if pgrep -x obs >/dev/null 2>&1; then obs_running=1; fi
    obs_found=0
    if command -v obs >/dev/null 2>&1; then
        obs_found=1
        say "OBS Studio $(obs --version 2>/dev/null | sed -n 's/^OBS Studio - \([0-9][0-9.]*\).*/\1/p' | head -1) found ($(command -v obs))."
        if ! ls /usr/lib/obs-plugins/obs-browser.so /usr/lib/*/obs-plugins/obs-browser.so /usr/lib64/obs-plugins/obs-browser.so \
                /usr/local/lib/obs-plugins/obs-browser.so >/dev/null 2>&1; then
            note "This OBS has no Browser Source (Ubuntu's and Debian's own OBS package leaves it out), so the on-stream widgets"
            note "can't show in it. OBS from Flathub, or from the OBS Project's PPA on Ubuntu, has it."
        fi
        websocket_step "$CONFIG_HOME/obs-studio/plugin_config/obs-websocket/config.json"
    fi
    if command -v flatpak >/dev/null 2>&1 && flatpak info com.obsproject.Studio >/dev/null 2>&1; then
        obs_found=1
        say 'OBS Studio from Flathub found. CrossChat runs outside its sandbox; the OBS script starts it there.'
        websocket_step "$FLATPAK_OBS/plugin_config/obs-websocket/config.json"
    fi
    if [ "$obs_found" = 0 ]; then
        note 'OBS Studio was not found (neither an obs program nor OBS from Flathub).'
        websocket_step "$CONFIG_HOME/obs-studio/plugin_config/obs-websocket/config.json"
    fi
else
    if [ -d /Applications/OBS.app ]; then
        say "OBS Studio $(defaults read /Applications/OBS.app/Contents/Info CFBundleShortVersionString 2>/dev/null || true) found."
    else
        note 'OBS Studio was not found in Applications.'
    fi
    if pgrep -xq OBS; then obs_running=1; fi
    websocket_step "$HOME/Library/Application Support/obs-studio/plugin_config/obs-websocket/config.json"
fi

# ---- Applications > CrossChat (Mac) or the app menu (Linux): what the Start menu has on Windows ----------
if [ "$LINUX" = 1 ]; then
    step 'App menu'
    mkdir -p "$SHORTCUTS"
    rm -f "$SHORTCUTS"/crosschat-*.desktop
    entry() {        # entry FILE NAME TERMINAL EXEC: a crosschat-FILE.desktop in the app menu
        printf '[Desktop Entry]\nType=Application\nName=%s\nIcon=%s\nExec=%s\nTerminal=%s\nCategories=AudioVideo;\n' \
            "$2" "$APP/extension/icons/icon-128.png" "$4" "$3" > "$SHORTCUTS/crosschat-$1.desktop" || note "Could not add \"$2\"."
    }
    control_entry() {  # control_entry FILE NAME COMMAND: runs hub/control.py COMMAND
        entry "$1" "$2" false "$(desktop_arg "$VENV_PY") $(desktop_arg "$APP/hub/control.py") $3"
    }
    control_entry open-chat 'CrossChat: Open chat' show
    control_entry demo 'CrossChat: Try the demo' demo
    control_entry theme-studio 'CrossChat: Theme Studio' studio
    control_entry x-live 'CrossChat: Go live on X' x-live
    control_entry x-dry 'CrossChat: Test X (never goes live)' x-dry
    control_entry unfeature 'CrossChat: Hide featured message' unfeature
    entry folder 'CrossChat folder' false "xdg-open $(desktop_arg "$APP")"
    entry uninstall 'Uninstall CrossChat' true "bash $(desktop_arg "$APP/scripts/uninstall.sh")"
    if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database "$SHORTCUTS" >/dev/null 2>&1 || true; fi
    say "Your app menu has CrossChat: Open chat, Theme Studio, Try the demo, Go live on X, and Uninstall CrossChat."
else
    step 'Applications'
    mkdir -p "$SHORTCUTS"
    rm -rf "$SHORTCUTS"/*.app
    PY_Q="$(applescript_text "$VENV_PY")"
    CONTROL_Q="$(applescript_text "$APP/hub/control.py")"
    APP_Q="$(applescript_text "$APP")"
    shortcut() {     # shortcut NAME APPLESCRIPT
        osacompile -o "$SHORTCUTS/$1.app" -e "$2" >/dev/null 2>&1 || note "Could not make the \"$1\" app."
    }
    control_app() {  # control_app NAME COMMAND: runs hub/control.py COMMAND
        shortcut "$1" "do shell script quoted form of \"$PY_Q\" & \" \" & quoted form of \"$CONTROL_Q\" & \" $2 > /dev/null 2>&1 &\""
    }
    control_app 'Open chat' show
    control_app 'Try the demo' demo
    control_app 'Theme Studio' studio
    control_app 'Go live on X' x-live
    control_app 'Test X (never goes live)' x-dry
    control_app 'Hide featured message' unfeature
    shortcut 'CrossChat folder' "do shell script \"open \" & quoted form of \"$APP_Q\""
    shortcut 'Uninstall CrossChat' "do shell script \"open \" & quoted form of \"$APP_Q/Uninstall.command\""
    say "Applications > CrossChat in your home folder ($SHORTCUTS): in Finder, Go > Home, then Applications > CrossChat."
fi

# ---- the hub that was running for an open OBS: start the updated one in its place ------------------------
# (OBS from Flathub holds its hub's input instead: there the OBS script's watchdog starts the updated hub by itself)
if [ -n "$restart_for" ]; then
    obs_pid="$(printf '%s' "$restart_for" | sed -n 's/.*--obs-pid \([0-9][0-9]*\).*/\1/p')"
    obs_config="$(printf '%s' "$restart_for" | sed -n 's/.*--obs-config \(.*\)$/\1/p')"
    if [ -z "$obs_config" ] && [ "$LINUX" = 1 ]; then obs_config="$CONFIG_HOME/obs-studio"; fi
    if [ -z "$obs_config" ]; then obs_config="$HOME/Library/Application Support/obs-studio"; fi
    if [ -n "$obs_pid" ] && kill -0 "$obs_pid" 2>/dev/null; then
        (cd "$APP/hub" && nohup "$VENV_PY" "$APP/hub/hub.py" --obs-pid "$obs_pid" --obs-config "$obs_config" >/dev/null 2>&1 &)
        say 'Started the updated hub for the OBS that is open.'
    fi
fi

# ---- the two steps that need you --------------------------------------------------------------------------
LUA="$APP/obs/crosschat.lua"
EXTENSION="$APP/extension"
STORE='https://chromewebstore.google.com/detail/crosschat/bnjoldkacppoejikoiccgkblbajbenhj'
if [ "$LINUX" = 1 ]; then
    copied=0                    # the script's path on the clipboard, with whichever tool this desktop has
    if [ -n "${WAYLAND_DISPLAY:-}" ] && command -v wl-copy >/dev/null 2>&1 && printf '%s' "$LUA" | wl-copy 2>/dev/null; then copied=1
    elif [ -n "${DISPLAY:-}" ] && command -v xclip >/dev/null 2>&1 && printf '%s' "$LUA" | xclip -selection clipboard 2>/dev/null; then copied=1
    elif [ -n "${DISPLAY:-}" ] && command -v xsel >/dev/null 2>&1 && printf '%s' "$LUA" | xsel --clipboard --input 2>/dev/null; then copied=1
    fi
    printf '\n\033[32m  Two steps left, about a minute:\033[0m\n\n'
    if [ "$copied" = 1 ]; then
        say '  1. OBS: Tools > Scripts > + and pick this file. Its path is on your clipboard: in the file window press'
        say '     Ctrl+L, paste, Enter.'
    else
        say '  1. OBS: Tools > Scripts > + and pick this file (in the file window, Ctrl+L lets you type or paste a path):'
    fi
    say "       $LUA"
    say '     OBS from Flathub sees this folder too: the same path works there.'
    say '  2. The browser extension, from the Chrome Web Store (Chrome, Chromium or Brave; in Edge, allow extensions'
    say '     from other stores first):'
    say "       $STORE"
    say '     Or load it unpacked: chrome://extensions > Developer mode > Load unpacked, and pick this folder:'
    say "       $EXTENSION"
    say '     (Needed for X, TikTok, Facebook and Instagram chat, for replies except on Twitch and Kick, and for X Live.)'
    say ''
    say '  On-stream widgets: in OBS add a Browser Source with one of these addresses:'
    say '       http://127.0.0.1:4466/overlay/chat       450 x 800'
    say '       http://127.0.0.1:4466/overlay/featured   900 x 260'
    say '       http://127.0.0.1:4466/overlay/viewers    600 x 120'
    say '       http://127.0.0.1:4466/overlay/alerts     800 x 300'
    say '  Restyle them with "CrossChat: Theme Studio" in your app menu.'
    say ''
    say '  Tell us what works and what doesn'"'"'t on your Linux at https://github.com/RandyNorthrup/crosschat-obs/issues'
    if [ "$obs_running" = 1 ]; then
        note '  OBS is open: after adding the script, it starts by itself. Already added? Press "Start the hub again" in Tools > Scripts.'
    fi
    if [ "$QUIET" != 1 ] && { [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; } && confirm 'Open the extension in the Chrome Web Store now?'; then
        opened=0                                  # in a browser the store works in, when there is one
        for browser in google-chrome google-chrome-stable chromium chromium-browser brave-browser microsoft-edge; do
            if command -v "$browser" >/dev/null 2>&1; then
                (nohup "$browser" "$STORE" >/dev/null 2>&1 &)
                opened=1
                break
            fi
        done
        [ "$opened" = 1 ] || xdg-open "$STORE" >/dev/null 2>&1 || true
    fi
else
    printf '%s' "$LUA" | pbcopy 2>/dev/null || true
    printf '\n\033[32m  Two steps left, about a minute:\033[0m\n\n'
    say '  1. OBS: Tools > Scripts > + and pick this file. Its path is on your clipboard: in the file window press'
    say '     Cmd+Shift+G, paste, Return.'
    say "       $LUA"
    say '  2. The browser extension, from the Chrome Web Store (in Edge, allow extensions from other stores first):'
    say "       $STORE"
    say '     Or load it unpacked: chrome://extensions > Developer mode > Load unpacked, and pick this folder'
    say '     (Cmd+Shift+G works there too):'
    say "       $EXTENSION"
    say '     (Needed for X, TikTok, Facebook and Instagram chat, for replies except on Twitch and Kick, and for X Live.)'
    say ''
    say '  On-stream widgets: in OBS add a Browser Source with one of these addresses:'
    say '       http://127.0.0.1:4466/overlay/chat       450 x 800'
    say '       http://127.0.0.1:4466/overlay/featured   900 x 260'
    say '       http://127.0.0.1:4466/overlay/viewers    600 x 120'
    say '       http://127.0.0.1:4466/overlay/alerts     800 x 300'
    say '  Restyle them in Applications > CrossChat > Theme Studio.'
    say ''
    say '  Tell us what works on your Mac and what doesn'"'"'t at'
    say '  https://github.com/RandyNorthrup/crosschat-obs/issues'
    if [ "$obs_running" = 1 ]; then
        note '  OBS is open: after adding the script, it starts by itself. Already added? Press "Start the hub again" in Tools > Scripts.'
    fi
    if [ "$QUIET" != 1 ] && confirm 'Open the extension in the Chrome Web Store now?'; then
        open -a 'Google Chrome' "$STORE" 2>/dev/null || open -a 'Microsoft Edge' "$STORE" 2>/dev/null || open "$STORE" || true
    fi
fi
printf '\033[32mCrossChat %s is installed.\033[0m\n' "$VERSION"
