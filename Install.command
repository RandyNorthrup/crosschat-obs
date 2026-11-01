#!/bin/bash
# CrossChat installer for macOS. In Terminal: type "bash ", drag this file into the window, press Return (macOS won't
# open a download that Apple hasn't signed with a double-click). It runs scripts/install.sh.
cd "$(dirname "$0")" || exit 1
/bin/bash scripts/install.sh "$@"
echo
read -r -p 'Press Return to close this window. ' _ </dev/tty
