"""Rumble's official Live Stream API for CrossChat: chat, Rants, subs and the viewer count of the streamer's live.

Rumble gives each streamer a private URL (rumble.com/account/livestream-api) that answers with that data as JSON. The
URL works like a password, so CrossChat keeps it in rumble.bin, encrypted for the current Windows user (DPAPI; on a Mac,
under a key in the login Keychain), never logs it, and never puts it in an error message. Rumble's answer also holds the stream key; only chat, Rants, subs and
the viewer count are used from it.
"""
import json
import os
import re
import urllib.parse

import requests

from twitch_api import protect, unprotect

ADDRESS = re.compile(r"https://rumble\.com/-livestream-api/get-data\?[^\s#]{8,600}")


class RumbleError(Exception):
    pass


class Rumble:
    """The streamer's Live Stream API URL. Blocking calls: the hub runs them in a worker thread."""

    def __init__(self, path):
        self.path, self.url, self.why = path, "", ""
        try:
            with open(path, "rb") as f:
                self.url = json.loads(unprotect(f.read()).decode()).get("url", "")
        except (OSError, ValueError):
            pass

    def on(self):
        return bool(self.url)

    def state(self):
        return {"state": "on" if self.url else ("error" if self.why else "off"), "why": self.why}

    def set(self, url):
        url = str(url or "").strip()
        parts = urllib.parse.urlsplit(url)
        if not ADDRESS.fullmatch(url) or not urllib.parse.parse_qs(parts.query).get("key"):
            raise RumbleError("That isn't a Rumble Live Stream API URL. Copy it from rumble.com/account/livestream-api.")
        data = protect(json.dumps({"url": url}).encode())
        with open(self.path + ".tmp", "wb") as f:
            f.write(data)
        os.replace(self.path + ".tmp", self.path)
        self.url, self.why = url, ""

    def forget(self):
        self.url, self.why = "", ""
        try:
            os.remove(self.path)
        except OSError:
            pass

    def fetch(self):
        """Rumble's answer, as a dict. RumbleError when Rumble refuses the URL (revoked or wrong)."""
        if not self.url:
            raise RumbleError("Rumble is not connected.")
        try:
            r = requests.get(self.url, timeout=10, headers={"Accept": "application/json"})
        except requests.RequestException:
            raise RumbleError("Rumble did not answer.") from None     # (the exception text would hold the URL)
        if r.status_code in (401, 403, 404):
            self.why = "Rumble refused the Live Stream API URL. Make a new one at rumble.com/account/livestream-api."
            raise RumbleError(self.why)
        if r.status_code != 200:
            raise RumbleError("Rumble answered %d." % r.status_code)
        try:
            data = r.json()
        except ValueError:
            raise RumbleError("Rumble's answer wasn't readable.") from None
        if not isinstance(data, dict):
            raise RumbleError("Rumble's answer wasn't readable.")
        return data
