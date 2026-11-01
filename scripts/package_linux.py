"""Builds the Linux (beta) download: dist/CrossChat-<version>-linux.tar.gz and its .sha256 file.

  python scripts/package_linux.py

Standard library only, so it runs on the release job (which installs nothing) on any system. The archive keeps Unix
file modes (scripts/install.sh runnable), and every entry has the same owner and time, so the same sources make the
same archive, byte for byte.
"""
import gzip
import hashlib
import io
import json
import os
import re
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDERS = ("extension", "hub", "obs")
FILES = ("config.example.json", "README.md", "CHANGELOG.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "SECURITY.md",
         "scripts/install.sh", "scripts/uninstall.sh", "docs/THEMES.md", "docs/COMPANION.md", "docs/API.md")
RUNNABLE = (".sh",)
STAMP = 1767225600                           # 2026-01-01 00:00:00 UTC, for every entry


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
    """(path in the archive, file on disk) for everything in the download, sorted."""
    found = [(name, os.path.join(ROOT, *name.split("/"))) for name in FILES]
    for folder in FOLDERS:
        for here, dirs, files in os.walk(os.path.join(ROOT, folder)):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for file in files:
                path = os.path.join(here, file)
                found.append((os.path.relpath(path, ROOT).replace(os.sep, "/"), path))
    return sorted(found)


def entry(name, size, mode, kind=tarfile.REGTYPE):
    info = tarfile.TarInfo(name)
    info.size, info.mode, info.type, info.mtime = size, mode, kind, STAMP
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def main():
    name = "CrossChat-%s-linux" % version()
    dist = os.path.join(ROOT, "dist")
    os.makedirs(dist, exist_ok=True)
    target = os.path.join(dist, name + ".tar.gz")
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        folders = sorted({"/".join(inside.split("/")[:i]) for inside, _ in contents() for i in range(1, inside.count("/") + 1)})
        tar.addfile(entry(name, 0, 0o755, tarfile.DIRTYPE))
        for folder in folders:
            tar.addfile(entry(name + "/" + folder, 0, 0o755, tarfile.DIRTYPE))
        for inside, path in contents():
            with open(path, "rb") as f:
                data = f.read()
            runnable = inside.endswith(RUNNABLE)
            if runnable:
                data = data.replace(b"\r\n", b"\n")        # a script with Windows line ends doesn't run
            tar.addfile(entry(name + "/" + inside, len(data), 0o755 if runnable else 0o644), io.BytesIO(data))
    with open(target, "wb") as out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=STAMP, compresslevel=9) as z:
            z.write(raw.getvalue())
    with open(target, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(target + ".sha256", "w", encoding="ascii", newline="") as f:
        f.write("%s  %s.tar.gz" % (digest, name))
    print(target)
    print("sha256", digest)


if __name__ == "__main__":
    main()
