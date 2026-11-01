#!/bin/bash
# CrossChat uninstaller for macOS. Run Uninstall.command (in the CrossChat folder, or Applications > CrossChat).
#   --quiet   ask nothing: keep a backup of your settings and themes, then remove everything else
QUIET=0
if [ "${1:-}" = "--quiet" ]; then QUIET=1; fi

APP="$HOME/Library/Application Support/CrossChat"
SHORTCUTS="$HOME/Applications/CrossChat"

printf '\n  Uninstall CrossChat\n'
if [ "$QUIET" != 1 ]; then
    read -r -p 'Remove CrossChat from this Mac? (y/n) ' sure </dev/tty || sure=n
    case "$sure" in [yY]*) ;; *) echo 'Nothing was changed.'; exit 0 ;; esac
fi

ps -axo pid=,command= | sed 's/^ *//' | while IFS= read -r line; do
    case "${line#* }" in *"$APP/"*hub*.py*) kill "${line%% *}" 2>/dev/null ;; esac
done

keep="$HOME/Documents/CrossChat backup"
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

# CrossChat's key in the login Keychain (it locked the saved sign-ins): removed by the Python that made it, so macOS
# doesn't ask, else by the security tool.
if ! "$APP/.venv/bin/python3" -c 'import sys; sys.path.insert(0, sys.argv[1]); import vault; sys.exit(0 if vault.forget_key() else 1)' \
        "$APP/hub" >/dev/null 2>&1; then
    security delete-generic-password -s CrossChat -a 'file key' >/dev/null 2>&1 || true
fi
rm -rf "$SHORTCUTS"
rm -rf "$APP"

printf '\n\033[32mCrossChat is removed. Two things only you can remove:\033[0m\n'
echo '  - OBS: Tools > Scripts, select crosschat.lua, press the minus button.'
echo '  - Chrome or Edge: the extensions page, CrossChat, Remove.'
