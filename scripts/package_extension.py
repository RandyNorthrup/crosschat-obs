"""Builds the Chrome Web Store upload: dist/CrossChat-extension-<version>.zip, manifest.json at its root.

  python scripts/package_extension.py

Standard library only. It refuses what the Web Store would refuse at upload (a description over 132 characters, a
"key" or "update_url", a missing file), so that shows up here rather than on the dashboard. Every entry has the same
time, so the same sources make the same zip, byte for byte.
"""
import hashlib
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAMP = (2026, 1, 1, 0, 0, 0)                # for every entry
NAME_MOST, DESCRIPTION_MOST = 75, 132        # the Web Store's limits on these two manifest fields
SKIP = {"__pycache__", ".DS_Store", "Thumbs.db"}


def referenced(manifest):
    """Every file the manifest names, as paths inside the extension."""
    found = list((manifest.get("icons") or {}).values())
    worker = (manifest.get("background") or {}).get("service_worker")
    if worker:
        found.append(worker)
    for script in manifest.get("content_scripts") or []:
        found += script.get("js") or []
        found += script.get("css") or []
    return found


def problems(manifest, folder):
    """What the Web Store would turn down in this manifest, as sentences ([] when nothing)."""
    out = []
    if manifest.get("manifest_version") != 3:
        out.append("manifest_version must be 3")
    if not 0 < len(manifest.get("name") or "") <= NAME_MOST:
        out.append("name must be 1 to %d characters" % NAME_MOST)
    description = manifest.get("description") or ""
    if not 0 < len(description) <= DESCRIPTION_MOST:
        out.append("description is %d characters; the Web Store takes 1 to %d" % (len(description), DESCRIPTION_MOST))
    if not re.fullmatch(r"\d{1,5}(\.\d{1,5}){0,3}", str(manifest.get("version") or "")):
        out.append("version must be one to four numbers separated by dots")
    for key in ("key", "update_url"):
        if key in manifest:
            out.append('"%s" is not allowed in an upload' % key)
    if "128" not in (manifest.get("icons") or {}):
        out.append("a 128 x 128 icon is required")
    for name in referenced(manifest):
        if not os.path.isfile(os.path.join(folder, *name.split("/"))):
            out.append("the manifest names %s, which is not there" % name)
    return out


def contents(folder):
    """(path in the zip, file on disk) for everything in the extension, sorted."""
    found = []
    for here, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for file in files:
            if file not in SKIP:
                path = os.path.join(here, file)
                found.append((os.path.relpath(path, folder).replace(os.sep, "/"), path))
    return sorted(found)


def build(folder, dist):
    """Check the extension in `folder` and zip it into `dist`. Returns the zip's path."""
    with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    wrong = problems(manifest, folder)
    if wrong:
        raise ValueError("; ".join(wrong))
    os.makedirs(dist, exist_ok=True)
    target = os.path.join(dist, "CrossChat-extension-%s.zip" % manifest["version"])
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for inside, path in contents(folder):
            info = zipfile.ZipInfo(inside, STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(path, "rb") as f:
                z.writestr(info, f.read())
    return target


def main():
    try:
        target = build(os.path.join(ROOT, "extension"), os.path.join(ROOT, "dist"))
    except ValueError as error:
        sys.exit("Not ready for the Chrome Web Store: %s" % error)
    with open(target, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    print(target)
    print("sha256", digest)


if __name__ == "__main__":
    main()
