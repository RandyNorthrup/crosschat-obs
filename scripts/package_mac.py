"""Builds the macOS download: dist/CrossChat-<version>-mac.zip and its .sha256 file.

  python scripts/package_mac.py

Standard library only, so it runs on the release job (which installs nothing) on any system. The zip keeps Unix file
modes, so Install.command and Uninstall.command open with a double-click once Finder has unpacked it.
"""
import hashlib
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDERS = ("extension", "hub", "obs")
FILES = ("Install.command", "Uninstall.command", "config.example.json", "README.md", "CHANGELOG.md", "LICENSE", "THIRD_PARTY_NOTICES.md",
         "scripts/install.sh", "scripts/uninstall.sh", "docs/THEMES.md", "docs/COMPANION.md", "docs/API.md")
RUNNABLE = (".command", ".sh")
STAMP = (2026, 1, 1, 0, 0, 0)                # every entry gets the same time, so the same sources make the same zip


def version():
    with open(os.path.join(ROOT, "hub", "hub.py"), encoding="utf-8") as f:
        hub = re.search(r'^VERSION = "(.+)"', f.read(), re.M).group(1)
    with open(os.path.join(ROOT, "extension", "manifest.json"), encoding="utf-8") as f:
        extension = json.load(f)["version"]
    with open(os.path.join(ROOT, "obs", "crosschat.lua"), encoding="utf-8") as f:
        lua = re.search(r'^local VERSION = "(.+)"', f.read(), re.M).group(1)
    if not hub == extension == lua:
        sys.exit("Versions differ: hub %s, extension %s, OBS script %s" % (hub, extension, lua))
    return hub


def contents():
    """(path in the zip, file on disk) for everything in the download, sorted."""
    found = [(name, os.path.join(ROOT, *name.split("/"))) for name in FILES]
    for folder in FOLDERS:
        for here, dirs, files in os.walk(os.path.join(ROOT, folder)):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for file in files:
                path = os.path.join(here, file)
                found.append((os.path.relpath(path, ROOT).replace(os.sep, "/"), path))
    return sorted(found)


def main():
    name = "CrossChat-%s-mac" % version()
    dist = os.path.join(ROOT, "dist")
    os.makedirs(dist, exist_ok=True)
    target = os.path.join(dist, name + ".zip")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for inside, path in contents():
            with open(path, "rb") as f:
                data = f.read()
            runnable = inside.endswith(RUNNABLE)
            if runnable:
                data = data.replace(b"\r\n", b"\n")        # a script with Windows line ends doesn't run on a Mac
            entry = zipfile.ZipInfo(name + "/" + inside, STAMP)
            entry.create_system = 3                        # Unix, so the modes below count
            entry.external_attr = (0o100755 if runnable else 0o100644) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(entry, data)
    with open(target, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(target + ".sha256", "w", encoding="ascii", newline="") as f:
        f.write("%s  %s.zip" % (digest, name))
    print(target)
    print("sha256", digest)


if __name__ == "__main__":
    main()
