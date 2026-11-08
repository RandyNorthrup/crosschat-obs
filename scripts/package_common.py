"""What scripts/package_mac.py and scripts/package_linux.py share: the version, and the files that go in a download.

Standard library only, as they are.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDERS = ("extension", "hub", "obs")


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


def contents(files):
    """(path in the download, file on disk) for `files` and everything in the program folders, sorted."""
    found = [(name, os.path.join(ROOT, *name.split("/"))) for name in files]
    for folder in FOLDERS:
        for here, dirs, names in os.walk(os.path.join(ROOT, folder)):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for file in names:
                path = os.path.join(here, file)
                found.append((os.path.relpath(path, ROOT).replace(os.sep, "/"), path))
    return sorted(found)
