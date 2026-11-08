"""Kick's official API for CrossChat: sending chat messages and moderating, as the signed-in streamer.

Sign-in is Kick's OAuth 2.1 code flow with PKCE: CrossChat opens Kick's authorize page in the browser, Kick sends the
browser back to the hub (http://localhost:<port>/kick/callback) with a one-time code, and the hub trades it for a
token. The tokens are kept in kick.bin, encrypted for the current Windows user (DPAPI; on a Mac, under a key in the login
Keychain; on Linux, under a key in the desktop keyring), like Twitch's, and not kept at all when they can't be.
"""
import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse

import requests

from config_file import replace_file
from vault import protect, refusal, unprotect, unreadable

ID = "https://id.kick.com/oauth"
API = "https://api.kick.com/public/v1"
SCOPES = "user:read channel:read chat:write moderation:ban moderation:chat_message:manage"
PENDING_SECONDS = 600


class KickError(Exception):
    pass


class Kick:
    """One signed-in Kick account. Blocking calls: the hub runs them in a worker thread."""

    def __init__(self, client_id, client_secret, path, redirect_uri):
        self.client_id, self.client_secret, self.path, self.redirect_uri = client_id, client_secret, path, redirect_uri
        self.tokens, self.user, self.pending, self.why = {}, {}, None, ""
        self.broadcasters = {}
        try:
            with open(path, "rb") as f:
                saved = json.loads(unprotect(f.read()).decode())
            self.tokens, self.user = saved.get("tokens", {}), saved.get("user", {})
        except FileNotFoundError:
            pass
        except (OSError, ValueError, AttributeError) as error:
            self.why = unreadable(error, "Kick sign-in")

    def state(self):
        if not self.client_id:
            return {"state": "off", "why": "This CrossChat has no Kick app Client ID."}
        if self.pending and time.time() < self.pending["expires"]:
            return {"state": "pending", "url": self.pending["url"]}
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
            raise KickError(self.why) from None
        replace_file(self.path, data)

    def _client(self, form):
        form["client_id"] = self.client_id
        if self.client_secret:
            form["client_secret"] = self.client_secret
        return form

    # ---- sign-in: authorization code with PKCE ---------------------------------------------------------------
    def start(self):
        """The Kick page to open in the browser."""
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(24)
        url = ID + "/authorize?" + urllib.parse.urlencode({
            "response_type": "code", "client_id": self.client_id, "redirect_uri": self.redirect_uri, "scope": SCOPES,
            "code_challenge": challenge, "code_challenge_method": "S256", "state": state})
        self.why = ""
        self.pending = {"verifier": verifier, "state": state, "url": url, "expires": time.time() + PENDING_SECONDS}
        return url

    def finish(self, code, state):
        """Kick sent the browser back: trade the code for tokens. The state must be the one this hub started."""
        p = self.pending
        if not p or time.time() > p["expires"] or not secrets.compare_digest(str(state), p["state"]):
            raise KickError("That Kick sign-in doesn't match one CrossChat started. Press Connect Kick again.")
        self.pending = None
        r = requests.post(ID + "/token", timeout=15, data=self._client({
            "grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri, "code_verifier": p["verifier"]}))
        if r.status_code != 200:
            self.why = "Kick did not sign in (%s)." % _message(r)
            raise KickError(self.why)
        d = r.json()
        self.tokens = {"access_token": d["access_token"], "refresh_token": d.get("refresh_token", "")}
        me = (self.call("GET", "/users").get("data") or [{}])[0]
        self.user = {"id": me.get("user_id"), "login": me.get("name", "")}
        self.save()

    def refresh(self):
        r = requests.post(ID + "/token", timeout=15, data=self._client({"grant_type": "refresh_token",
                                                                         "refresh_token": self.tokens.get("refresh_token", "")}))
        if r.status_code != 200:
            self.tokens, self.why = {}, "Kick signed CrossChat out. Connect Kick again."
            try:
                os.remove(self.path)
            except OSError:
                pass
            raise KickError(self.why)
        d = r.json()
        self.tokens = {"access_token": d["access_token"], "refresh_token": d.get("refresh_token", self.tokens.get("refresh_token", ""))}
        self.save()

    def forget(self):
        """Sign out: the tokens are deleted here and revoked at Kick. False when Kick didn't confirm it."""
        tokens = self.tokens
        self.tokens, self.user, self.pending, self.why = {}, {}, None, ""
        try:
            os.remove(self.path)
        except OSError:
            pass
        done = True
        for kind in ("refresh_token", "access_token"):
            if tokens.get(kind):
                try:                             # Kick takes these as query parameters
                    r = requests.post(ID + "/revoke", params={"token": tokens[kind], "token_hint_type": kind}, timeout=10,
                                      headers={"Content-Type": "application/x-www-form-urlencoded"})
                    done = done and r.status_code == 200
                except requests.RequestException:
                    done = False
        return done

    # ---- the API -------------------------------------------------------------------------------------------
    def call(self, method, path, params=None, body=None, retry=True):
        if not self.tokens.get("access_token"):
            raise KickError("Kick is not connected.")
        r = requests.request(method, API + path, params=params, json=body, timeout=15,
                             headers={"Authorization": "Bearer " + self.tokens["access_token"], "Accept": "application/json"})
        if r.status_code == 401 and retry and self.tokens.get("refresh_token"):
            self.refresh()
            return self.call(method, path, params, body, retry=False)
        if r.status_code >= 400:
            raise KickError(_message(r))
        return r.json() if r.text.strip() else {}

    def broadcaster(self, slug):
        """The channel's user id: the configured channel, else the signed-in streamer's own."""
        key = slug or ""
        if key not in self.broadcasters:
            found = (self.call("GET", "/channels", {"slug": slug} if slug else None).get("data") or [])
            if not found:
                raise KickError("There is no Kick channel called %s." % slug)
            self.broadcasters[key] = found[0]["broadcaster_user_id"]
        return self.broadcasters[key]

    def send(self, slug, text, reply_to=""):
        body = {"content": text, "type": "user", "broadcaster_user_id": self.broadcaster(slug)}
        if reply_to:
            body["reply_to_message_id"] = reply_to
        sent = self.call("POST", "/chat", body=body).get("data") or {}
        if sent.get("is_sent") is False:
            raise KickError("Kick did not post it.")

    def moderate(self, slug, action, user_id="", message_id="", seconds=0, reason=""):
        who = {"broadcaster_user_id": self.broadcaster(slug)}
        if action == "delete":
            self.call("DELETE", "/chat/" + urllib.parse.quote(str(message_id), safe=""))
        elif action in ("timeout", "ban"):
            body = {**who, "user_id": int(user_id)}
            if reason:
                body["reason"] = reason[:100]
            if action == "timeout":                 # Kick counts timeouts in whole minutes: 1 minute to 7 days
                body["duration"] = max(1, min(-(-int(seconds or 600) // 60), 10080))
            self.call("POST", "/moderation/bans", body=body)
        elif action == "unban":
            self.call("DELETE", "/moderation/bans", body={**who, "user_id": int(user_id)})
        else:
            raise KickError("unknown action")


def _message(r):
    try:
        d = r.json()
        return d.get("message") or d.get("error_description") or d.get("error") or str(r.status_code)
    except ValueError:
        return "HTTP %d" % r.status_code
