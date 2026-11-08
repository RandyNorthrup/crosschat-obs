"""Paired devices for the CrossChat companion (a phone, tablet or other PC on the home network).

Pairing: the chat window on the streaming PC asks for a 6-digit code (it lasts five minutes and allows five wrong
tries). The device that enters it gets a long random token, kept in an HttpOnly cookie. Only the SHA-256 of each
token is stored here, so devices.json is no use to anyone who copies it. Revoking a device deletes its hash.
"""
import hashlib
import hmac
import json
import os
import secrets
import time

import config_file

CODE_SECONDS = 300
CODE_TRIES = 5
SEEN_EVERY = 60                              # last_seen is written to disk at most this often per device


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Devices:
    def __init__(self, path, trouble=None):
        """trouble: told, in words for the streamer, when the saved list can't be used."""
        self.path = path
        self.code = None                     # {"code", "expires", "tries"} while a pairing is open
        self.devices = []
        try:
            with open(path, encoding="utf-8-sig") as f:
                self.devices = [d for d in json.load(f)["devices"] if isinstance(d, dict) and isinstance(d.get("hash"), str)]
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError) as error:   # kept, or the next save would wipe it for good
            kept = config_file.set_aside(path)
            if trouble:
                trouble("CrossChat couldn't read its list of paired devices (%s), so they need pairing again.%s" % (
                    error, " The damaged file is kept as %s.bad." % os.path.basename(path) if kept else ""))

    def save(self):
        config_file.replace_file(self.path, json.dumps({"devices": self.devices}, indent=1))

    def listing(self):
        return [{k: d.get(k) for k in ("id", "name", "created", "last_seen")} for d in self.devices]

    def start_pairing(self):
        self.code = {"code": "%06d" % secrets.randbelow(1000000), "expires": time.time() + CODE_SECONDS, "tries": 0}
        return self.code["code"], self.code["expires"]

    def pairing_open(self):
        return bool(self.code) and time.time() < self.code["expires"]

    def pair(self, code, name):
        """A new device token for the right code, or None. The code works once."""
        if not self.pairing_open():
            self.code = None
            return None
        if not hmac.compare_digest(str(code).strip(), self.code["code"]):
            self.code["tries"] += 1
            if self.code["tries"] >= CODE_TRIES:
                self.code = None             # too many wrong guesses: start again from the chat window
            return None
        self.code = None
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        name = " ".join(str(name or "").split())[:40] or "Device"
        self.devices.append({"id": secrets.token_hex(6), "name": name, "hash": digest(token), "created": now, "last_seen": now})
        self.save()
        return token

    def check(self, token):
        """The device a token belongs to, or None."""
        if not token:
            return None
        wanted = digest(token)
        for d in self.devices:
            if hmac.compare_digest(d["hash"], wanted):
                now = int(time.time())
                if now - d.get("last_seen", 0) > SEEN_EVERY:
                    d["last_seen"] = now
                    self.save()
                return d
        return None

    def revoke(self, device_id):
        before = len(self.devices)
        self.devices = [d for d in self.devices if d.get("id") != device_id]
        if len(self.devices) != before:
            self.save()
            return True
        return False


def device_name(user_agent):
    """A readable name for a new device from its browser's User-Agent."""
    ua = user_agent or ""
    for needle, name in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Macintosh", "Mac"),
                         ("Windows", "Windows PC"), ("CrOS", "Chromebook"), ("Linux", "Linux PC")):
        if needle in ua:
            return name
    return "Device"
