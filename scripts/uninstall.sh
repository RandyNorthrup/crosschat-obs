#!/bin/bash
# CrossChat uninstaller for macOS and Linux. On a Mac, run Uninstall.command (in the CrossChat folder, or Applications >
# CrossChat); on Linux, "Uninstall CrossChat" in the app menu, or: bash ~/.local/share/CrossChat/scripts/uninstall.sh
#   --quiet   ask nothing: keep a backup of your settings and themes, then remove everything else
QUIET=0
if [ "${1:-}" = "--quiet" ]; then QUIET=1; fi

LINUX=0
if [ "$(uname -s)" = Linux ]; then LINUX=1; fi
if [ "$LINUX" = 1 ]; then
    DATA="${XDG_DATA_HOME:-}"
    case "$DATA" in /*) ;; *) DATA="$HOME/.local/share" ;; esac
    APP="$DATA/CrossChat"
    SHORTCUTS="$DATA/applications"
    DOCUMENTS="$(xdg-user-dir DOCUMENTS 2>/dev/null || true)"
    if [ -z "$DOCUMENTS" ] || [ "$DOCUMENTS" = "$HOME" ]; then DOCUMENTS="$HOME/Documents"; fi
    MACHINE='computer'
else
    APP="$HOME/Library/Application Support/CrossChat"
    SHORTCUTS="$HOME/Applications/CrossChat"
    DOCUMENTS="$HOME/Documents"
    MACHINE='Mac'
fi

printf '\n  Uninstall CrossChat\n'
if [ "$QUIET" != 1 ]; then
    read -r -p "Remove CrossChat from this $MACHINE? (y/n) " sure </dev/tty || sure=n
    case "$sure" in [yY]*) ;; *) echo 'Nothing was changed.'; exit 0 ;; esac
fi

ps -axo pid=,command= | sed 's/^ *//' | while IFS= read -r line; do
    case "${line#* }" in *"$APP/"*hub*.py*) kill "${line%% *}" 2>/dev/null ;; esac
done

keep="$DOCUMENTS/CrossChat backup"
mine=()
for item in config.json themes; do
    if [ -e "$APP/$item" ]; then mine+=("$APP/$item"); fi
done
if [ "${#mine[@]}" -gt 0 ]; then
    save=y
    if [ "$QUIET" != 1 ]; then read -r -p "Keep your settings and themes in \"$keep\"? (y/n) [y] " save </dev/tty || save=y; fi
    case "$save" in
        [nN]*) ;;
        *) mkdir -p "$keep" && cp -R "${mine[@]}" "$keep/" && echo "Kept in $keep" ;;
    esac
fi

# CrossChat's key (it locked the saved sign-ins): removed by the Python that made it, so the system doesn't ask, else by
# the system's own tool (macOS: the login Keychain; Linux: the desktop keyring, through secret-tool).
if ! "$APP/.venv/bin/python3" -c 'import sys; sys.path.insert(0, sys.argv[1]); import vault; sys.exit(0 if vault.forget_key() else 1)' \
        "$APP/hub" >/dev/null 2>&1; then
    if [ "$LINUX" = 1 ]; then
        secret-tool clear service CrossChat account 'file key' >/dev/null 2>&1 || true
    else
        security delete-generic-password -s CrossChat -a 'file key' >/dev/null 2>&1 || true
    fi
fi
if [ "$LINUX" = 1 ]; then
    rm -f "$SHORTCUTS"/crosschat-*.desktop
else
    rm -rf "$SHORTCUTS"
fi
rm -rf "$APP"

printf '\n\033[32mCrossChat is removed. Two things only you can remove:\033[0m\n'
echo '  - OBS: Tools > Scripts, select crosschat.lua, press the minus button.'
echo '  - Your browser: the extensions page, CrossChat, Remove.'
