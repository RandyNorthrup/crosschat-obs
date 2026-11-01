"""Twitch's official API for CrossChat: sending chat messages and moderating, as the signed-in streamer.

Sign-in uses Twitch's device code flow for public apps: CrossChat shows a short code, the streamer enters it at
twitch.tv/activate, and Twitch hands CrossChat a token. There is no client secret. The tokens are kept in
twitch.bin, encrypted with Windows' DPAPI for the current Windows user (on a Mac: under a key in the login Keychain;
on Linux: under a key in the desktop keyring; see vault.py), so the file is useless on another account or PC. When they
can't be encrypted (Linux without a keyring), the sign-in isn't kept at all.
"""
import json
import os
import time

import requests

from vault import protect, refusal, unprotect

ID = "https://id.twitch.tv/oauth2"
API = "https://api.twitch.tv/helix"
SCOPES = "user:write:chat moderator:manage:banned_users moderator:manage:chat_messages"


class TwitchError(Exception):
    pass


class Twitch:
    """One signed-in Twitch account. Blocking calls: the hub runs them in a worker thread."""

    def __init__(self, client_id, path):
        self.client_id, self.path = client_id, path
        self.tokens = {}                         # access_token, refresh_token
        self.user = {}                           # id, login
        self.pending = None                      # the device code flow in progress
        self.why = ""
        self.broadcasters = {}                   # channel login -> user id
        try:
            with open(path, "rb") as f:
                saved = json.loads(unprotect(f.read()).decode())
            self.tokens, self.user = saved.get("tokens", {}), saved.get("user", {})
        except (OSError, ValueError):
            pass

    # ---- state ---------------------------------------------------------------------------------------------
    def state(self):
        if not self.client_id:
            return {"state": "off", "why": "This CrossChat has no Twitch app Client ID."}
        if self.pending:
            return {"state": "pending", "user_code": self.pending["user_code"], "verification_uri": self.pending["verification_uri"]}
        if self.tokens.get("access_token"):
            return {"state": "on", "login": self.user.get("login", "")}
        return {"state": "error" if self.why else "off", "why": self.why}

    def on(self):
        return bool(self.client_id and self.tokens.get("access_token"))

    def save(self):
        try:
            data = protect(json.dumps({"tokens": self.tokens, "user": self.user}).encode())
        except OSError as error:                 # not kept safely: not kept at all, not even until CrossChat closes
            self.tokens, self.user, self.why = {}, {}, refusal(error)
            raise TwitchError(self.why) from None
        with open(self.path + ".tmp", "wb") as f:
            f.write(data)
        os.replace(self.path + ".tmp", self.path)

    def forget(self):
        """Sign out: the tokens are deleted here and revoked at Twitch. False when Twitch didn't confirm it."""
        token = self.tokens.get("access_token")
        self.tokens, self.user, self.pending, self.why = {}, {}, None, ""
        try:
            os.remove(self.path)
        except OSError:
            pass
        if not token:
            return True
        try:                                     # tell Twitch too, so the token stops working everywhere
            r = requests.post(ID + "/revoke", data={"client_id": self.client_id, "token": token}, timeout=10)
            return r.status_code == 200 or (r.status_code == 400 and "invalid token" in r.text.lower())
        except requests.RequestException:
            return False

    # ---- sign-in: device code flow -------------------------------------------------------------------------
    def start(self):
        r = requests.post(ID + "/device", data={"client_id": self.client_id, "scopes": SCOPES}, timeout=15)
        if r.status_code != 200:
            raise TwitchError("Twitch refused to start the sign-in (%s)" % r.status_code)
        d = r.json()
        self.why = ""
        page = str(d.get("verification_uri") or "")
        if not page.startswith("https://www.twitch.tv/"):       # only ever send the streamer to Twitch's own page
            page = "https://www.twitch.tv/activate"
        self.pending = {"device_code": d["device_code"], "user_code": d["user_code"], "verification_uri": page,
                        "interval": max(int(d.get("interval", 5)), 1), "expires": time.time() + int(d.get("expires_in", 1800))}
        return self.pending

    def poll(self):
        """One check of a sign-in in progress: True when signed in, False while waiting. Raises when it failed."""
        p = self.pending
        if not p:
            raise TwitchError("No sign-in is in progress.")
        if time.time() > p["expires"]:
            self.pending = None
            raise TwitchError("The code ran out. Press Connect again.")
        r = requests.post(ID + "/token", timeout=15, data={"client_id": self.client_id, "scopes": SCOPES, "device_code": p["device_code"],
                                                           "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
        if r.status_code == 400 and "authorization_pending" in r.text:
            return False
        if r.status_code != 200:
            self.pending = None
            raise TwitchError("Twitch did not sign in (%s)." % (r.json().get("message", r.status_code) if r.text.startswith("{") else r.status_code))
        d = r.json()
        self.pending = None
        self.tokens = {"access_token": d["access_token"], "refresh_token": d.get("refresh_token", "")}
        me = self.call("GET", "/users")["data"][0]
        self.user = {"id": me["id"], "login": me["login"]}
        self.save()
        return True

    def refresh(self):
        r = requests.post(ID + "/token", timeout=15, data={"client_id": self.client_id, "grant_type": "refresh_token",
                                                           "refresh_token": self.tokens.get("refresh_token", "")})
        if r.status_code != 200:
            self.tokens, self.why = {}, "Twitch signed CrossChat out. Connect Twitch again."
            try:
                os.remove(self.path)
            except OSError:
                pass
            raise TwitchError(self.why)
        d = r.json()
        self.tokens = {"access_token": d["access_token"], "refresh_token": d.get("refresh_token", self.tokens.get("refresh_token", ""))}
        self.save()

    # ---- the API -------------------------------------------------------------------------------------------
    def call(self, method, path, params=None, body=None, retry=True):
        if not self.tokens.get("access_token"):
            raise TwitchError("Twitch is not connected.")
        r = requests.request(method, API + path, params=params, json=body, timeout=15,
                             headers={"Client-Id": self.client_id, "Authorization": "Bearer " + self.tokens["access_token"]})
        if r.status_code == 401 and retry:
            self.refresh()
            return self.call(method, path, params, body, retry=False)
        if r.status_code >= 400:
            try:
                message = r.json().get("message") or r.reason
            except ValueError:
                message = r.reason
            raise TwitchError(message)
        return r.json() if r.text else {}

    def broadcaster(self, channel):
        if channel not in self.broadcasters:
            found = self.call("GET", "/users", {"login": channel})["data"]
            if not found:
                raise TwitchError("There is no Twitch channel called %s." % channel)
            self.broadcasters[channel] = found[0]["id"]
        return self.broadcasters[channel]

    def send(self, channel, text, reply_to=""):
        body = {"broadcaster_id": self.broadcaster(channel), "sender_id": self.user["id"], "message": text}
        if reply_to:
            body["reply_parent_message_id"] = reply_to
        sent = (self.call("POST", "/chat/messages", body=body).get("data") or [{}])[0]
        if not sent.get("is_sent"):
            raise TwitchError(((sent.get("drop_reason") or {}).get("message")) or "Twitch did not post it.")

    def moderate(self, channel, action, user_id="", message_id="", seconds=0, reason=""):
        who = {"broadcaster_id": self.broadcaster(channel), "moderator_id": self.user["id"]}
        if action == "delete":
            self.call("DELETE", "/moderation/chat", {**who, "message_id": message_id})
        elif action in ("timeout", "ban"):
            data = {"user_id": user_id, "reason": reason[:500]}
            if action == "timeout":
                data["duration"] = max(1, min(int(seconds or 600), 1209600))
            self.call("POST", "/moderation/bans", who, {"data": data})
        elif action == "unban":
            self.call("DELETE", "/moderation/bans", {**who, "user_id": user_id})
        else:
            raise TwitchError("unknown action")
