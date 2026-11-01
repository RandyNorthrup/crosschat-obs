"""The update notice, off unless the streamer switches it on: once a day CrossChat asks GitHub which CrossChat release is
the newest, and when it is newer than this one the window shows a line with a link to that release's page.

The question is one plain HTTPS request to a fixed address on GitHub's public API, with no cookies and nothing about the
streamer in it; GitHub sees the PC's IP address, as with any web request. CrossChat never downloads or installs
anything: the link goes to the release page on GitHub, and the streamer decides.
"""
import json
import re

import requests

REPO = "RandyNorthrup/crosschat-obs"
ADDRESS = "https://api.github.com/repos/%s/releases/latest" % REPO
PAGE = "https://github.com/%s/releases/tag/v%s"
DAY = 24 * 3600                              # seconds between two questions, at most one a day
MOST = 1024 * 1024                           # bytes of GitHub's answer read at most
NUMBER = re.compile(r"v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})")    # 1.7.0 or v1.7.0; nothing else counts as a release


class UpdateError(Exception):
    pass


def version(text):
    """(major, minor, patch) for "1.7.0" or "v1.7.0"; None for anything else, a pre-release like "1.7.0-rc1" included."""
    found = NUMBER.fullmatch(str(text or "").strip())
    return tuple(int(n) for n in found.groups()) if found else None


def page(numbers):
    """The release page on GitHub, made here from the version numbers (never a link taken from the answer)."""
    return PAGE % (REPO, "%d.%d.%d" % numbers)


def newest(current, get=requests.get):
    """{"version", "url"} of the newest CrossChat release when it is newer than `current`, else None. UpdateError when
    GitHub can't be asked or its answer isn't a release. Blocking: the hub runs it in a worker thread."""
    mine = version(current)
    if not mine:
        raise UpdateError("This CrossChat has no plain version number.")
    try:
        r = get(ADDRESS, timeout=10, stream=True, allow_redirects=False,
                headers={"User-Agent": "CrossChat/%s" % current, "Accept": "application/vnd.github+json"})
    except requests.RequestException:
        raise UpdateError("GitHub did not answer.") from None
    try:
        if r.status_code != 200:
            raise UpdateError("GitHub answered %d." % r.status_code)
        try:
            body = r.raw.read(MOST + 1, decode_content=True)
        except Exception:                    # a connection cut halfway, a broken compression: no answer
            raise UpdateError("GitHub's answer didn't arrive whole.") from None
    finally:
        r.close()
    if len(body) > MOST:
        raise UpdateError("GitHub's answer was too big.")
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise UpdateError("GitHub's answer wasn't readable.") from None
    if not isinstance(data, dict):
        raise UpdateError("GitHub's answer wasn't readable.")
    if data.get("draft") is not False or data.get("prerelease") is not False:
        return None                          # GitHub's "latest" is never either; anything else is no release to point at
    theirs = version(data.get("tag_name"))
    if not theirs:
        raise UpdateError("GitHub's newest release has no plain version number.")
    return {"version": "%d.%d.%d" % theirs, "url": page(theirs)} if theirs > mine else None
