"""Discord, outgoing only: CrossChat posts to one channel of the streamer's Discord server through a webhook (Discord:
Server Settings → Integrations → Webhooks → New Webhook → Copy Webhook URL). No bot and no Discord sign-in: a webhook
can only post in its own channel.

What goes there is the streamer's choice: a going-live notice, the messages shown on stream, and all chat. Only what
viewers already see on stream: never messages hidden by filters, notes, tests or anything about this PC. Chat can never
ping anyone (allowed_mentions is empty and every @ is broken up), Discord formatting is shown as typed, and links in
chat can't be clicked or previewed.

The webhook URL works like a password (anyone who has it can post in that channel), so CrossChat keeps it in
discord.bin, encrypted for the current Windows user (DPAPI; on a Mac or Linux, see vault.py), never logs it, never
shows it again and never puts it in an error message. When it can't be encrypted, it isn't kept.
"""
import asyncio
import collections
import json
import logging
import os
import re
import urllib.parse

import requests

from twitch_api import protect, unprotect

ADDRESS = re.compile(r"https://(?:discord\.com|discordapp\.com|ptb\.discord\.com|canary\.discord\.com)/api/webhooks/(\d{15,22})/([\w-]{30,100})")
CHOICES = {"live": True, "featured": True, "chat": False}     # what is posted, until the streamer picks
POST_MOST = 1900                             # characters in one post (Discord takes 2000)
LINE_MOST = 400                              # characters of one chat line
GAP = 2.0                                    # seconds between two posts: Discord takes 30 a minute in one channel
BACKLOG = 600                                # chat lines waiting at most; when chat outruns Discord the oldest go
TRIES = 5                                    # attempts at one post before it is dropped
SUPPRESS_EMBEDS, SUPPRESS_NOTIFICATIONS = 1 << 2, 1 << 12
HELLO = "CrossChat is connected to this channel. What you picked in CrossChat's Settings gets posted here while you're live."
MARKDOWN = re.compile(r"([\\*_~`|\[\]()<>#-])")
LINK = re.compile(r"https?://\S+|www\.\S+", re.I)
log = logging.getLogger("crosschat")


class DiscordError(Exception):
    pass


class RateLimited(DiscordError):
    def __init__(self, seconds):
        super().__init__("Discord asked to wait %.1f s" % seconds)
        self.seconds = seconds


class Gone(DiscordError):
    pass


def plain(text):
    """Chat text as Discord shows it literally: one line, formatting characters escaped, no working @mentions, and
    links in `code` (shown, but not clickable and not previewed)."""
    text = " ".join(str(text or "").split())
    out, at = [], 0
    for found in LINK.finditer(text):
        out.append(MARKDOWN.sub(r"\\\1", text[at:found.start()]))
        out.append("`%s`" % found.group().replace("`", ""))
        at = found.end()
    out.append(MARKDOWN.sub(r"\\\1", text[at:]))
    return "".join(out).replace("@", "@​")


def cut(text, most):
    chars = list(text)
    return text if len(chars) <= most else "".join(chars[:most - 1]) + "…"


def shown(m):
    """A chat message or event viewers see on stream (the ones Discord may get)."""
    return (isinstance(m, dict) and m.get("type", "msg") == "msg" and m.get("kind") in ("chat", "event") and m.get("p") != "system"
            and not m.get("hidden") and not m.get("test"))


def line(m, names):
    """One message as a line in Discord: **name** (Platform): text."""
    who = "**%s** (%s)" % (plain(cut(str(m.get("name") or "someone"), 60)), names.get(m.get("p"), str(m.get("p"))))
    if m.get("kind") == "event":
        said = " ".join(t for t in (str(m.get("system") or ""), str(m.get("text") or "")) if t)
        return cut("%s %s" % (who, plain(said)), LINE_MOST)
    return cut("%s: %s" % (who, plain(m.get("text"))), LINE_MOST)


class Discord:
    """The streamer's webhook and what to post through it. base: a test server standing in for discord.com."""

    def __init__(self, path, names, base="", changed=None):
        self.path, self.names, self.base = path, names, base
        self.changed = changed                   # called (in the hub's loop) when Discord drops the webhook
        self.url, self.name, self.why, self.choices = "", "", "", dict(CHOICES)
        self.waiting, self.lines, self.dropped, self.wake = collections.deque(), 0, 0, None
        try:
            with open(path, "rb") as f:
                saved = json.loads(unprotect(f.read()).decode())
            self.url, self.name = saved.get("url", ""), str(saved.get("name") or "")[:80]
            self.choices = {k: saved.get(k, v) is True for k, v in CHOICES.items()}
        except (OSError, ValueError, AttributeError):
            pass

    def on(self):
        return bool(self.url) and not self.why

    def state(self):
        return {"state": "on" if self.on() else ("error" if self.why else "off"), "why": self.why, "name": self.name, **self.choices}

    # ---- connecting --------------------------------------------------------------------------------------------------
    def target(self, url=None):
        url = url or self.url
        return self.base + urllib.parse.urlsplit(url).path if self.base else url

    def save(self):
        data = protect(json.dumps({"url": self.url, "name": self.name, **self.choices}).encode())
        with open(self.path + ".tmp", "wb") as f:
            f.write(data)
        os.replace(self.path + ".tmp", self.path)

    def set(self, url, choices=None):
        """Check the webhook with Discord, then keep it. Blocking: the hub runs it in a worker thread."""
        url = str(url or "").strip()
        found = ADDRESS.fullmatch(url)
        if not found:
            raise DiscordError("That isn't a Discord webhook URL. In Discord: Server Settings → Integrations → Webhooks → Copy Webhook URL.")
        data = self.ask(url)
        if str(data.get("id")) != found.group(1):
            raise DiscordError("Discord's answer was about another webhook.")
        self.url, self.name, self.why = url, str(data.get("name") or "")[:80], ""
        self.clear()
        try:
            self.choose(choices)
        except OSError:                          # not kept safely (vault.py): not kept at all
            self.url, self.name = "", ""
            raise

    def ask(self, url):
        """Discord's description of the webhook (its name), which also proves it exists."""
        try:
            r = requests.get(self.target(url), timeout=10, allow_redirects=False, headers={"User-Agent": "CrossChat"})
        except requests.RequestException:
            raise DiscordError("Discord did not answer.") from None     # (the exception text would hold the URL)
        if r.status_code in (401, 403, 404):
            raise DiscordError("Discord doesn't know that webhook. Copy it again in Discord (it may have been deleted).")
        if r.status_code != 200:
            raise DiscordError("Discord answered %d." % r.status_code)
        try:
            data = r.json()
        except ValueError:
            raise DiscordError("Discord's answer wasn't readable.") from None
        if not isinstance(data, dict):
            raise DiscordError("Discord's answer wasn't readable.")
        return data

    def choose(self, choices):
        if isinstance(choices, dict):
            self.choices = {k: (choices.get(k) is True) if k in choices else v for k, v in self.choices.items()}
        if self.url:
            self.save()

    def forget(self):
        self.url, self.name, self.why = "", "", ""
        self.clear()
        try:
            os.remove(self.path)
        except OSError:
            pass

    # ---- what goes to Discord ---------------------------------------------------------------------------------------
    def clear(self):
        self.waiting.clear()
        self.lines = self.dropped = 0

    def queue(self, item):
        self.waiting.append(item)
        if item[0] == "line":
            self.lines += 1
            if self.lines > BACKLOG:                 # chat faster than Discord takes it: the oldest line goes
                oldest = next(i for i, x in enumerate(self.waiting) if x[0] == "line")
                del self.waiting[oldest]
                self.lines -= 1
                self.dropped += 1
        if self.wake:
            self.wake.set()

    def live(self, text):
        """The going-live notice (text made by the hub, with links to the streamer's own channels)."""
        if self.on() and self.choices["live"]:
            self.queue(("post", text, 0))

    def featured(self, m):
        if self.on() and self.choices["featured"] and shown(m):
            self.queue(("post", "⭐ On stream: " + line(m, self.names), SUPPRESS_EMBEDS))

    def chat(self, m):
        if self.on() and self.choices["chat"] and shown(m):
            self.queue(("line", line(m, self.names)))

    def next_post(self):
        """The next post: one notice, or as many chat lines as fit."""
        kind, text, *rest = self.waiting[0]
        if kind == "post":
            self.waiting.popleft()
            return {"content": text, "allowed_mentions": {"parse": []}, "flags": rest[0]}
        parts = []
        if self.dropped:
            parts.append("_(%d messages skipped: chat was faster than Discord takes it)_" % self.dropped)
            self.dropped = 0
        size = sum(len(p) + 1 for p in parts)
        while self.waiting and self.waiting[0][0] == "line" and size + len(self.waiting[0][1]) + 1 <= POST_MOST:
            text = self.waiting.popleft()[1]
            self.lines -= 1
            parts.append(text)
            size += len(text) + 1
        return {"content": "\n".join(parts), "allowed_mentions": {"parse": []}, "flags": SUPPRESS_EMBEDS | SUPPRESS_NOTIFICATIONS}

    def post(self, payload):
        """One post. Blocking: run in a worker thread. RateLimited when Discord says to wait, Gone when the webhook no
        longer exists (nothing more is posted until it is connected again)."""
        if not self.url:
            raise DiscordError("Discord is not connected.")
        try:
            r = requests.post(self.target(), json=payload, timeout=10, allow_redirects=False, headers={"User-Agent": "CrossChat"})
        except requests.RequestException:
            raise DiscordError("Discord did not answer.") from None
        if r.status_code in (200, 204):
            return
        if r.status_code == 429:
            try:
                seconds = float(r.json().get("retry_after"))
            except (ValueError, TypeError, AttributeError):
                try:
                    seconds = float(r.headers.get("Retry-After") or 5)
                except ValueError:
                    seconds = 5.0
            raise RateLimited(min(max(seconds, 0.05), 300))
        if r.status_code in (401, 403, 404):
            self.why = "Discord no longer takes posts from this webhook (it, or its channel, was deleted). Connect a new one."
            self.clear()
            raise Gone(self.why)
        raise DiscordError("Discord answered %d." % r.status_code)

    async def send(self, payload, sleep=asyncio.sleep):
        """Post it, waiting when Discord asks and trying again a few times when Discord is down. True when posted."""
        wait = 2
        for _ in range(TRIES):
            try:
                await asyncio.to_thread(self.post, payload)
                return True
            except RateLimited as limited:
                await sleep(limited.seconds)
            except Gone:
                log.warning("Discord: %s", self.why)
                if self.changed:
                    self.changed()
                return False
            except DiscordError as error:
                log.info("Discord: %s Trying again in %d s.", error, wait)
                await sleep(wait)
                wait = min(wait * 2, 60)
            if not self.url:                     # disconnected meanwhile
                return False
        log.warning("Discord: a post was dropped after %d tries", TRIES)
        return False

    async def run(self, sleep=asyncio.sleep):
        """Post what is waiting, one post at a time and at most one every GAP seconds, for good (the hub runs it under
        keep_running)."""
        self.wake = asyncio.Event()
        while True:
            if not self.waiting or not self.on():
                self.wake.clear()
                await self.wake.wait()
                continue
            await self.send(self.next_post(), sleep)
            await sleep(GAP)
