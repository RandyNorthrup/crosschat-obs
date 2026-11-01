#!/bin/bash
# CrossChat uninstaller for macOS: double-click this file. It runs scripts/uninstall.sh in Terminal.
cd "$(dirname "$0")" || exit 1
/bin/bash scripts/uninstall.sh "$@"
echo
read -r -p 'Press Return to close this window. ' _ </dev/tty
