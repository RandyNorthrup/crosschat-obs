#!/bin/bash
# CrossChat installer for macOS (beta): double-click this file. It runs scripts/install.sh in Terminal.
cd "$(dirname "$0")" || exit 1
/bin/bash scripts/install.sh "$@"
echo
read -r -p 'Press Return to close this window. ' _ </dev/tty
