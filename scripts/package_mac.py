"""Builds the macOS download: dist/CrossChat-<version>-mac.zip and its .sha256 file.

  python scripts/package_mac.py

Standard library only, so it runs on the release job (which installs nothing) on any system. The zip keeps Unix file
modes, so Install.command and Uninstall.command open with a double-click once Finder has unpacked it.
"""
import hashlib
import os
import zipfile

from package_common import ROOT, contents, version

FILES = ("Install.command", "Uninstall.command", "config.example.json", "README.md", "CHANGELOG.md", "LICENSE", "THIRD_PARTY_NOTICES.md",
         "scripts/install.sh", "scripts/uninstall.sh", "docs/THEMES.md", "docs/COMPANION.md", "docs/API.md")
RUNNABLE = (".command", ".sh")
STAMP = (2026, 1, 1, 0, 0, 0)                # every entry gets the same time, so the same sources make the same zip


def main():
    name = "CrossChat-%s-mac" % version()
    dist = os.path.join(ROOT, "dist")
    os.makedirs(dist, exist_ok=True)
    target = os.path.join(dist, name + ".zip")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for inside, path in contents(FILES):
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
