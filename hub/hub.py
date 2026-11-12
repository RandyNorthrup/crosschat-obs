"""CrossChat hub: the chat of every platform the stream goes to, in one window, following your streaming app.

OBS starts this (obs/crosschat.lua) and it leaves when OBS closes; for other streaming apps see follow_app. When the
stream starts it opens the chat window; it closes the window a little while after the stream ends. With the CrossChat browser extension it also
starts and ends the livestream on X and posts the replies typed in the chat window.

Settings are in config.json in the folder above this one (see config.example.json).

  python hub.py --test [--twitch NAME] [--youtube @HANDLE_OR_CHANNEL_ID] [--kick SLUG[:CHATROOM_ID]]
      run without OBS, as if a stream had just started (for trying it against any public channel)
  python hub.py --demo             a made-up live stream on every platform: try every page; replies and moderation
                                   "work" but nothing leaves this PC
  python hub.py --config PATH      another settings file
  python hub.py --obs-config DIR   OBS's settings folder (the OBS script passes it, so portable OBS works too)
  python hub.py --obs-pid PID      stay until that OBS closes (the OBS script passes it)
  python hub.py --obs-stdin        stay until standard input ends (the OBS script, in OBS from Flathub, holds its other end)
  python hub.py --quiet            no message boxes, only the log
"""
import asyncio
import collections
import concurrent.futures
import ctypes
import base64
import datetime
import hashlib
import json
import logging
import logging.handlers
import os
import random
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid

import requests
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

import config_file
import emotes as emote_sources
import settings_ui
import tailscale
import updates
import vault
import viewers as viewer_cards
from chatlog import ChatLog
from devices import Devices, device_name
from discord_relay import HELLO, SUPPRESS_NOTIFICATIONS, Discord, DiscordError
from kick_api import Kick, KickError
from rumble_api import Rumble, RumbleError
from twitch_api import Twitch, TwitchError

MAC = sys.platform == "darwin"               # macOS: the few Windows-only jobs are done the Mac way, in macos.py
LINUX = sys.platform.startswith("linux")     # Linux: the same jobs done the Linux way, in linux.py
if MAC:
    import macos
elif LINUX:
    import linux
else:
    from ctypes import wintypes

VERSION = "1.9.1"
# CrossChat's public Twitch app (Client ID only: public apps have no secret). "twitch_client_id" in config.json overrides it.
TWITCH_CLIENT_ID = "gg5cmjfvr1l09niyes19ccclashuth"  # gitleaks:allow (a public client ID, not a secret)
# CrossChat's Kick app. Kick requires the app's secret even with PKCE, so it ships here and is not confidential: Kick
# only ever returns sign-ins to http://localhost:4466/kick/callback on the streamer's own PC. "kick_client_id" and
# "kick_client_secret" in config.json switch to your own Kick app.
KICK_CLIENT_ID = "01M69ZK8VQP2AR2SXBVXCC02AF"  # gitleaks:allow (public app id)
# Stored scrambled so credential-scraping bots that search GitHub for keys pass it by. It is not encryption.
KICK_CLIENT_SECRET = bytes(b ^ 0x5A for b in base64.b64decode("bDxqY2g8OGtuOz85O2poPz87Ym4+bj44Yjs4Yjloa2o8ajk8PmNjP245YzxvbG8/bGtrO2ttb2M7aTtsaWNibg=="))[::-1].decode()  # gitleaks:allow  # noqa: E501
HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)                  # the CrossChat folder: config.json, the log, the extension, your themes
WEB = os.path.join(HERE, "web")
PRESETS = os.path.join(HERE, "presets")      # the themes that come with CrossChat (read-only)
TITLE = "CrossChat · chat"                  # the chat window is found again by this title (window.html has it too)
THEME_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
WIDGETS = ("chat", "featured", "viewers", "alerts")
NO_WINDOW = 0x08000000
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}
log = logging.getLogger("crosschat")

DEFAULTS = {
    "port": 4466,
    "twitch": "",
    "youtube": "",
    "kick": "",
    "kick_chatroom": 0,
    "tiktok": "",                            # your TikTok @name: its LIVE page opens in your browser when you go live
    "tiktok_window": "auto",                 # where that page goes: "auto" (under the chat window) or {"x", "y", "width", "height"}
    "facebook": False,                       # true: Facebook Live chat, from Live Producer in your browser (it opens when you go live)
    "facebook_window": "auto",
    "instagram": False,                      # true: Instagram Live comments, from its Live producer in your browser
    "instagram_window": "auto",
    "rumble_window": "auto",                 # where Rumble's chat pop-out goes (replies are typed there)
    "browser": "auto",                       # "auto" (Chrome, else Edge), "chrome", "edge" or the full path of a browser
    "window": "auto",                        # "auto" (right edge of the main screen) or {"x", "y", "width", "height"}
    "open_window_on_stream_start": True,
    "close_window_seconds_after_stream": 120,
    "overlay": {"platforms": "all", "theme": "classic"},
    "broadcaster": "auto",                   # the streaming app to follow: "auto", "obs", "streamlabs" or "manual" (see follow_app)
    "obs": {"host": "127.0.0.1", "port": 0, "password": ""},     # port 0 and no password: read from OBS's own settings
    "remote": {"enabled": True, "port": 4467, "tailscale": False},  # the companion for paired devices; tailscale: also away from home
    "updates": {"check": False},             # true: ask GitHub once a day whether a newer CrossChat is out (nothing else is sent)
    "twitch_client_id": "",
    "kick_client_id": "",                    # your own Kick app instead of CrossChat's (both or neither)
    "kick_client_secret": "",
    "custom_overlays": "",                   # a folder of your own overlay pages, served at /custom/ (see custom_file)
    "emotes": {"bttv": True, "ffz": True, "7tv": True},
    "logs": {"enabled": True, "keep_days": 90},  # every stream's chat in logs/, to search and export later
    "x": {
        "enabled": False,
        "auto_go_live": False,
        "delay_seconds": 12,
        "title": "Live now",
        "title_file": "",
        "title_prefix": "",
        "post": "",
        "source": "OBS",
        "end_with_obs": True,
        "end_seconds_after_obs": 15,
        "window": "auto",
    },
}

ARGV, CFG, X = [], {}, {}
HOME = APP                                   # your folder: config.json, crosschat.log and themes/ (the one config.json is in)
CONFIG_PATH = os.path.join(APP, "config.json")   # the config.json in use (Settings → Channels & options writes it)
TEST, PORT = False, DEFAULTS["port"]
DEMO = False                                 # --demo: a made-up live stream, for trying CrossChat without going live
TWITCH = YOUTUBE = KICK = TIKTOK = ""
FACEBOOK = INSTAGRAM = False
KICK_ROOM = 0
problems = []                                # what went wrong before there was anywhere to say it: start_log writes it down, main shows it


def arg(name, default):
    return ARGV[ARGV.index(name) + 1] if name in ARGV[:-1] else default


def merged(base, over):
    """`over` laid on top of `base`, section by section."""
    out = {}
    for key, value in base.items():
        mine = over.get(key, value) if isinstance(over, dict) else value
        out[key] = merged(value, mine) if isinstance(value, dict) and isinstance(mine, dict) else mine
    if isinstance(over, dict):
        out.update({k: v for k, v in over.items() if k not in base})
    return out


def channel(value, platform):
    """A channel the way people paste it (a name, an @handle, a channel id or a link), cleaned up; '' when unusable."""
    value = str(value or "").strip()
    if platform == "youtube":
        found = re.search(r"(?:^|/)(@[\w.-]{3,30}|UC[\w-]{22})(?:$|[/?#])", value)
        if found:
            return found.group(1)
        return "@" + value if re.fullmatch(r"[\w.-]{3,30}", value) else ""
    value = re.sub(r"^(?:https?://)?(?:www\.)?(?:twitch\.tv|kick\.com|tiktok\.com)/", "", value, flags=re.I)
    value = re.split(r"[/?#]", value)[0].lower().lstrip("@")
    pattern = {"twitch": r"[a-z0-9_]{1,25}", "tiktok": r"[a-z0-9_.]{2,24}"}.get(platform, r"[a-z0-9_-]{1,40}")
    return value if re.fullmatch(pattern, value) else ""


def number(name, given, default):
    """A setting that has to be a whole number. Anything else is noted and `default` used: a slip in config.json must
    not stop CrossChat."""
    try:
        return int(given)
    except (TypeError, ValueError):
        problems.append("config.json: \"%s\" should be a whole number, not %r. Using %s." % (name, given, default))
        return default


def configure(argv):
    """Settings: the defaults, then config.json (or --config PATH, or the file CROSSCHAT_CONFIG names), then the command
    line. What's wrong with them goes in `problems`: there is no log to tell yet."""
    global ARGV, CFG, X, HOME, CONFIG_PATH, TEST, DEMO, PORT, TWITCH, YOUTUBE, KICK, KICK_ROOM, TIKTOK, FACEBOOK, INSTAGRAM
    ARGV = list(argv)
    problems.clear()
    warned.clear()
    DEMO = "--demo" in ARGV
    path = os.path.abspath(arg("--config", os.environ.get("CROSSCHAT_CONFIG") or os.path.join(APP, "config.json")))
    HOME, CONFIG_PATH = os.path.dirname(path), path
    try:
        with open(path, encoding="utf-8-sig") as f:
            mine = json.load(f)
    except FileNotFoundError:
        mine = {}
    except (OSError, ValueError) as error:
        problems.append("config.json could not be read (%s), so CrossChat is using its defaults, with no channels set. Fix or delete the file." % error)
        mine = {}
    if not isinstance(mine, dict):
        problems.append("config.json isn't a settings file (it should be one { ... } block), so CrossChat is using its defaults.")
        mine = {}
    for name, value in DEFAULTS.items():
        if isinstance(value, dict) and mine.get(name) and not isinstance(mine[name], dict):
            problems.append("config.json: \"%s\" should be a { ... } section. Using its defaults." % name)
            del mine[name]
    CFG = merged(DEFAULTS, mine)
    for name, value in DEFAULTS.items():
        if isinstance(value, dict) and not CFG[name]:     # ("emotes": false and the like: that section is simply off)
            CFG[name] = {}
    X = CFG["x"] if CFG["x"].get("enabled") else {}
    TEST = "--test" in ARGV or DEMO
    PORT = number("port", arg("--port", CFG["port"]), DEFAULTS["port"])
    if not 0 < PORT < 65536:
        problems.append("config.json: %d isn't a port. Using %d." % (PORT, DEFAULTS["port"]))
        PORT = DEFAULTS["port"]
    for section in ("obs", "remote"):
        CFG[section]["port"] = number(section + ".port", CFG[section].get("port") or 0, DEFAULTS[section]["port"])
    CFG["logs"]["keep_days"] = number("logs.keep_days", CFG["logs"].get("keep_days") or DEFAULTS["logs"]["keep_days"], DEFAULTS["logs"]["keep_days"])
    TWITCH = channel(arg("--twitch", CFG["twitch"]), "twitch")
    YOUTUBE = channel(arg("--youtube", CFG["youtube"]), "youtube")
    KICK, KICK_ROOM = channel(CFG["kick"], "kick"), number("kick_chatroom", CFG["kick_chatroom"] or 0, 0)
    if "--kick" in ARGV:
        slug, _, room = arg("--kick", "").partition(":")
        KICK, KICK_ROOM = channel(slug, "kick"), number("--kick", room or 0, 0)
    TIKTOK = channel(CFG["tiktok"], "tiktok")
    FACEBOOK = CFG.get("facebook") is True or str(CFG.get("facebook")).lower() in ("on", "yes", "1")
    INSTAGRAM = CFG.get("instagram") is True or str(CFG.get("instagram")).lower() in ("on", "yes", "1")
    for name, given, used in (("twitch", CFG["twitch"], TWITCH), ("youtube", CFG["youtube"], YOUTUBE), ("kick", CFG["kick"], KICK),
                              ("tiktok", CFG["tiktok"], TIKTOK)):
        if given and not used:
            problems.append("config.json: %r is not a %s channel CrossChat can use, so %s is left out." % (given, name, name))


messages = collections.deque(maxlen=300)     # what a newly opened window is shown first
clients = set()                              # one queue per open window or companion
local_clients = set()                        # the ones on this PC (they see paired devices and pairing codes)
status = {}                                  # platform -> "off" | "waiting" | "on" | "retry"
viewers = {}                                 # platform -> people watching now (None when not live there)
streaming = asyncio.Event()
state = {"youtube_video": "", "youtube_chat": None, "since": 0.0, "featured": None, "executor": None}
starred = []                                 # message ids put aside to answer later (shared by every window and device)
QUESTION = re.compile(r"\?\s*\W*$|^\s*(what|how|why|when|where|who|which|can|could|would|will|is|are|do|does|did|should|any)\b", re.I)


def send(event, only=None):
    if event.get("type") in ("delete", "purge") and LOG:
        LOG.write(event)
    for q in list(only if only is not None else clients):
        q.put_nowait(event)


PUBLIC_EVENTS = ("msg", "delete", "purge", "clear", "hide", "emotes", "feature", "status", "theme", "viewers")


class PublicFeed(asyncio.Queue):
    """What your own overlay pages (custom_overlays) get from /events: the chat exactly as viewers see it on stream.
    Nothing about this PC, its accounts, paired devices, filters or replies, and no filtered messages or notes."""
    def put_nowait(self, event):
        kind = event.get("type")
        if kind == "hide":                       # filtered after it showed: to these pages, it's simply gone
            event = {"type": "delete", "id": event.get("id", "")}
        elif kind == "msg" and (event.get("hidden") or event.get("p") == "system" or event.get("kind") == "note"):
            return
        elif kind == "feature" and (event.get("msg") or {}).get("hidden"):
            return
        elif kind not in PUBLIC_EVENTS:
            return
        super().put_nowait(event)


seen = set()                                 # (platform, viewer) that have chatted this stream
health = {}                                  # platform -> {"since", "last", "reconnects"}


def hidden_reason(name, text, handle=""):
    """Which of the streamer's filters a message trips ("word", "user", "command", "bot"), or ''."""
    f = FILTERS
    who = {str(name).lower(), str(handle).lower()} - {""}
    if f.get("bots") and who & BOTS:
        return "bot"
    if who & {u.lower().lstrip("@") for u in f.get("users", [])}:
        return "user"
    if f.get("hide_commands") and text.lstrip().startswith("!"):
        return "command"
    lowered = " " + re.sub(r"[^\w']+", " ", text.lower()) + " "
    if any(" " + w.lower().strip() + " " in lowered for w in f.get("words", []) if w.strip()):
        return "word"
    return ""


def publish(platform, name, text, color="", badges=(), mid="", kind="chat", raw="", first="", **more):
    """raw: the platform's own message id (for moderating it). first: "ever" when the platform says it's the viewer's
    first message in the channel. more: emotes (Twitch's "id:from-to,..." list), handle (the @name on X), uid (the
    platform's user id), alert, amount, system and test, for the pages that use them."""
    now = time.time()
    event = {"type": "msg", "id": mid or "%s-%d" % (platform, time.time_ns()), "t": int(now * 1000),
             "p": platform, "name": name, "text": text, "color": color, "badges": list(badges), "kind": kind}
    event.update({k: v for k, v in more.items() if v})
    if raw:
        event["mid"] = raw
    if kind == "chat" and len(text) > 6 and QUESTION.search(text):
        event["question"] = True
    if kind == "chat" and platform != "system" and name:
        who = (platform, str(more.get("uid") or name).lower())
        if first or who not in seen:
            event["first"] = first or "stream"
        seen.add(who)
        reason = hidden_reason(name, text, more.get("handle", ""))
        if reason:
            event["hidden"] = reason
    if platform in health:
        health[platform]["last"] = int(now * 1000)
    messages.append(event)
    if LOG and kind != "note":
        LOG.write(event)
    send(event)
    speak_maybe(event)
    if to_discord():
        DC.chat(event)                           # (only if the streamer picked "all chat"; never hidden ones)


def status_event():
    return {"type": "status", "status": dict(status), "live": streaming.is_set(), "yt": state["youtube_video"],
            "health": {p: dict(h) for p, h in health.items()}}


def set_status(platform, value):
    if status.get(platform) != value:
        h = health.setdefault(platform, {"since": 0, "last": 0, "reconnects": 0})
        if value == "on":
            h["since"] = int(time.time() * 1000)
        elif value == "retry":
            h["since"] = 0
            h["reconnects"] += 1
        status[platform] = value
        log.info("%s chat: %s", platform, value)
        send(status_event())


def note(text):
    publish("system", "", text, kind="note")


def not_saved(error):
    """Why a secret (Rumble's API URL, the Discord webhook) wasn't kept: on Linux without a keyring, the keyring's
    story (vault.Unavailable), else the folder's."""
    return str(error) if isinstance(error, vault.Unavailable) else "Could not save it in your CrossChat folder."


warned = set()                               # what warn() has said already this stream


def warn(text, logged=False):
    """Tell the person at the PC: in the log, in the chat window and in a plain message box (the hub has no window of its
    own, so a problem would otherwise go unseen). The same words only once a stream. logged: the log has it already.
    Returns the message box's thread (None when there is no box to wait for)."""
    if text in warned:
        return None
    warned.add(text)
    if not logged:
        log.warning(text)
    note(text)
    if "--quiet" in ARGV:
        return None
    if MAC:
        target, args = macos.message_box, (text,)
    elif LINUX:
        target, args = linux.message_box, (text,)
    else:
        target, args = user32.MessageBoxW, (None, text, "CrossChat", 0x30 | 0x10000 | 0x40000)
    box = threading.Thread(target=target, args=args, daemon=True)
    box.start()
    return box


# ---- Twitch: anonymous read-only IRC --------------------------------------------------------------
def irc_tags(raw):
    out = {}
    for pair in raw.split(";"):
        k, _, v = pair.partition("=")
        out[k] = v.replace("\\s", " ").replace("\\:", ";").replace("\\\\", "\\")
    return out


# Twitch's USERNOTICE kinds, as the on-stream alerts know them; each with the tag that holds its number
TWITCH_ALERTS = {"sub": ("sub", ""), "resub": ("resub", "msg-param-cumulative-months"),
                 "subgift": ("gift", ""), "anonsubgift": ("gift", ""), "submysterygift": ("gift", "msg-param-mass-gift-count"),
                 "raid": ("raid", "msg-param-viewerCount")}


def twitch_notice(tags):
    """(alert, amount) for a USERNOTICE: a sub, resub, gift or raid, else ("other", "")."""
    alert, count = TWITCH_ALERTS.get(tags.get("msg-id", ""), ("other", ""))
    amount = tags.get(count, "") if count else ""
    if alert == "gift":                          # the alert says "gifted {amount}": the unit goes with the number
        amount = gifts(amount or "1", "sub")
    return alert, amount


def gifts(count, unit):
    """'a sub', '5 subs', '3 memberships'."""
    return ("a " + unit) if count in ("", "1") else "%s %ss" % (count, unit)


async def twitch(channel_name):
    wait = 2
    while True:
        writer = None
        try:
            set_status("twitch", "waiting")
            reader, writer = await asyncio.wait_for(asyncio.open_connection("irc.chat.twitch.tv", 6697, ssl=True), 20)
            writer.write(("CAP REQ :twitch.tv/tags twitch.tv/commands\r\nNICK justinfan%d\r\nJOIN #%s\r\n"
                          % (random.randint(10000, 99999), channel_name)).encode())
            await writer.drain()
            while True:
                line = (await asyncio.wait_for(reader.readline(), 400)).decode("utf-8", "replace").rstrip("\r\n")
                if not line:
                    break
                if line.startswith("PING"):
                    writer.write(b"PONG :tmi.twitch.tv\r\n")
                    await writer.drain()
                    continue
                try:
                    tags = {}
                    if line.startswith("@"):
                        raw, _, line = line[1:].partition(" ")
                        tags = irc_tags(raw)
                    parts = line.split(" ", 3)
                    command = parts[1] if len(parts) > 1 else ""
                    if command in ("366", "ROOMSTATE"):          # joined
                        set_status("twitch", "on")
                        wait = 2
                        if tags.get("room-id") and tags["room-id"] != state.get("twitch_room"):
                            state["twitch_room"] = tags["room-id"]          # the channel's own 7TV/BTTV/FFZ sets come by this id
                            spawn(load_emotes(tags["room-id"]))
                    elif command == "PRIVMSG" and len(parts) == 4:
                        text = parts[3][1:]
                        emotes = tags.get("emotes", "")
                        if text.startswith("\x01ACTION "):
                            text, emotes = text[8:].rstrip("\x01"), ""      # emote positions count from the full line
                        badges = [b.split("/")[0] for b in tags.get("badges", "").split(",") if b]
                        name = tags.get("display-name") or parts[0][1:].split("!")[0]
                        publish("twitch", name, text, tags.get("color", ""), badges, "tw-" + tags.get("id", ""), emotes=emotes,
                                raw=tags.get("id", ""), uid=tags.get("user-id", ""), first="ever" if tags.get("first-msg") == "1" else "")
                        if tags.get("bits", "").isdigit():       # a cheer is a chat line and an alert
                            publish("twitch", name, text, kind="event", alert="cheer", amount=tags["bits"] + " bits",
                                    system="%s cheered %s bits" % (name, tags["bits"]), mid="tw-cheer-" + tags.get("id", ""))
                    elif command == "USERNOTICE":                # subs, raids and the like
                        alert, amount = twitch_notice(tags)
                        said, system = parts[3][1:] if len(parts) == 4 else "", tags.get("system-msg", "")
                        # text is what the viewer said; Twitch's own sentence goes in system (the alerts write their own)
                        publish("twitch", tags.get("display-name", ""), said if alert != "other" else (system + "  " + said).strip(),
                                kind="event", alert=alert, amount=amount, system=system, mid="tw-" + tags.get("id", ""))
                    elif command == "CLEARMSG":
                        send({"type": "delete", "id": "tw-" + tags.get("target-msg-id", "")})
                    elif command == "CLEARCHAT" and len(parts) == 4:
                        send({"type": "purge", "p": "twitch", "name": parts[3][1:].lower()})
                    elif command == "RECONNECT":
                        break
                except (ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
                    skipped("twitch", error)
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError) as error:
            skipped("twitch", error, "chat connection dropped")
        finally:
            if writer:
                writer.close()
        set_status("twitch", "retry")
        await asyncio.sleep(wait)
        wait = min(wait * 2, 60)


def skipped(platform, error, doing="skipped a message CrossChat couldn't read"):
    """Something a platform did that CrossChat couldn't follow (the rest carries on), noted in the log once per kind of
    problem, so a platform changing its format shows up there."""
    key = (platform, doing, type(error).__name__, str(error)[:80])
    if key not in skipped.seen:
        skipped.seen.add(key)
        log.warning("%s: %s (%s: %s)", platform, doing, type(error).__name__, str(error)[:300])


skipped.seen = set()
background = set()                           # the jobs nobody waits for, while they run (the event loop only keeps weak references)


def spawn(job):
    """Start a job nobody waits for: it is kept until it ends, so it can't be collected half way, and a failure goes in the log."""
    task = asyncio.create_task(job)
    background.add(task)
    task.add_done_callback(spawned_done)
    return task


def spawned_done(task):
    background.discard(task)
    if not task.cancelled() and task.exception():
        log.error("a background job failed", exc_info=task.exception())


async def keep_running(name, job):
    """Run one of the hub's long jobs for good. If it ever stops on something unexpected, the problem goes in the log
    and the job starts again a moment later, so a chat never goes quiet for the rest of the stream."""
    wait = 2
    while True:
        started = time.time()
        try:
            return await job()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("%s stopped on something unexpected; starting it again", name)
            if name in NAMES:
                set_status(name, "retry")
        wait = 2 if time.time() - started > 300 else min(wait * 2, 60)
        await asyncio.sleep(wait)


# ---- YouTube: the same public requests the chat pop-out page makes --------------------------------
web = requests.Session()
web.headers.update(UA)
web.cookies.set("SOCS", "CAI", domain=".youtube.com")


def page_json(html, marker):
    """The JSON object assigned to `marker` inside a page."""
    at = html.find(marker)
    if at < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(html[html.index("{", at):])[0]
    except ValueError:
        return None


def yt_live_video(target):
    """Video id of the channel's stream if it is live (or about to be), else ''."""
    path = target if target.startswith("@") else "channel/" + target
    html = web.get("https://www.youtube.com/%s/live" % path, timeout=15).text
    found = re.search(r'"videoDetails":\{"videoId":"([\w-]{11})"', html)
    live = '"isLive":true' in html or '"isLiveNow":true' in html or '"isUpcoming":true' in html
    return found.group(1) if found and live else ""


def yt_every_message(chat):
    """The token for "Live chat" (every message) in the chat page's view menu, found by its name. '' when it isn't there:
    then YouTube shows "Top chat", which holds some messages back."""
    try:
        for item in chat["header"]["liveChatHeaderRenderer"]["viewSelector"]["sortFilterSubMenuRenderer"]["subMenuItems"]:
            title = item.get("title")
            if (title if isinstance(title, str) else yt_text(title)).strip().lower().startswith("live chat"):
                return item["continuation"]["reloadContinuationData"]["continuation"]
    except (KeyError, TypeError, AttributeError):
        pass
    return ""


def yt_open(video):
    html = web.get("https://www.youtube.com/live_chat?is_popout=1&v=" + video, timeout=15).text
    key = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html)
    version = re.search(r'"(?:INNERTUBE_CLIENT_VERSION|clientVersion)":"([^"]+)"', html)
    data = page_json(html, "ytInitialData")
    chat = ((data or {}).get("contents") or {}).get("liveChatRenderer")
    if not (key and version and chat):
        return None
    every = yt_every_message(chat)
    opened = {"key": key.group(1), "version": version.group(1), "token": every or next(iter(chat["continuations"][0].values()))["continuation"]}
    if not every:
        opened["top_only"] = True
    return opened


def yt_text(message):
    out = []
    for run in (message or {}).get("runs", []):
        if "text" in run:
            out.append(run["text"])
        elif "emoji" in run:
            emoji = run["emoji"]
            out.append(emoji["emojiId"] if not emoji.get("isCustomEmoji") else (emoji.get("shortcuts") or [""])[0])
    return "".join(out) or (message or {}).get("simpleText", "")


# YouTube chat items that are shown, and the alert each one is ("" for a plain chat line)
YT_KINDS = {"liveChatTextMessageRenderer": "", "liveChatPaidMessageRenderer": "superchat", "liveChatPaidStickerRenderer": "superchat",
            "liveChatMembershipItemRenderer": "member", "liveChatSponsorshipsGiftPurchaseAnnouncementRenderer": "gift"}


def yt_poll(chat):
    """Returns (events, seconds to wait), or None when the chat has ended."""
    reply = web.post("https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?prettyPrint=false&key=" + chat["key"],
                     json={"context": {"client": {"clientName": "WEB", "clientVersion": chat["version"], "hl": "en"}},
                           "continuation": chat["token"]}, timeout=15).json()
    body = (reply.get("continuationContents") or {}).get("liveChatContinuation")
    if not body or not body.get("continuations"):
        return None
    nxt = next(iter(body["continuations"][0].values()))
    chat["token"] = nxt["continuation"]
    events = []
    for action in body.get("actions", []):
        gone = action.get("removeChatItemAction") or action.get("markChatItemAsDeletedAction")
        if gone:
            events.append({"type": "delete", "id": "yt-" + gone.get("targetItemId", "")})
            continue
        item = (action.get("addChatItemAction") or {}).get("item") or {}
        for kind, r in item.items():
            if kind not in YT_KINDS:
                continue
            if kind == "liveChatSponsorshipsGiftPurchaseAnnouncementRenderer":     # the gifter's details sit in a header
                r = {**r, **((r.get("header") or {}).get("liveChatSponsorshipsHeaderRenderer") or {})}
            badges = []
            for b in r.get("authorBadges", []):
                b = b.get("liveChatAuthorBadgeRenderer", {})
                badges.append((b.get("icon") or {}).get("iconType", "member").lower())
            # text is what the viewer said; YouTube's own description of the event goes in system
            text, amount, system = yt_text(r.get("message")), yt_text(r.get("purchaseAmountText")), ""
            if kind == "liveChatPaidMessageRenderer":
                system = "Super Chat " + amount
            elif kind == "liveChatPaidStickerRenderer":
                system = "Super Sticker " + amount
            elif kind == "liveChatMembershipItemRenderer":
                system = yt_text(r.get("headerPrimaryText")) or yt_text(r.get("headerSubtext")) or "New member"
            elif kind == "liveChatSponsorshipsGiftPurchaseAnnouncementRenderer":
                system = yt_text(r.get("primaryText")) or "Gifted memberships"
                amount = gifts((re.search(r"\d+", system) or [""])[0], "membership")
            event = {"type": "msg", "id": "yt-" + r.get("id", ""), "name": yt_text(r.get("authorName")),
                     "text": text, "badges": badges, "usec": int(r.get("timestampUsec", 0)), "kind": "event" if YT_KINDS[kind] else "chat",
                     "uid": r.get("authorExternalChannelId", "")}
            if YT_KINDS[kind]:
                event.update(alert=YT_KINDS[kind], amount=amount, system=system.strip())
            events.append(event)
    return events, min(max(nxt.get("timeoutMs", 5000) / 1000, 1.5), 8)


async def youtube(target):
    seen = collections.deque(maxlen=2000)
    top_only_told = None                          # the stream the streamer was last told about Top chat
    while True:
        await streaming.wait()
        set_status("youtube", "waiting")
        began, video = time.time(), ""
        while streaming.is_set() and not video:       # YouTube takes a little while to notice the stream
            try:
                video = await asyncio.to_thread(yt_live_video, target)
            except (requests.RequestException, ValueError) as error:
                video = ""
                skipped("youtube", error, "couldn't look up the live video")
            if not video:
                await asyncio.sleep(10 if time.time() - began < 300 else 30)
        chat = None
        while streaming.is_set() and video and not chat:
            try:
                chat = await asyncio.to_thread(yt_open, video)
                if not chat:
                    skipped("youtube", LookupError("no chat on the live chat page"), "couldn't open the chat")
            except (requests.RequestException, ValueError, KeyError) as error:
                chat = None
                skipped("youtube", error, "couldn't open the chat")
            if not chat:
                await asyncio.sleep(15)
        if not chat:
            set_status("youtube", "off")
            continue
        state["youtube_video"], state["youtube_chat"] = video, chat
        set_status("youtube", "on")
        if chat.get("top_only") and top_only_told != state["since"]:
            top_only_told = state["since"]
            skipped("youtube", LookupError("no \"Live chat\" in its menu"), "showing Top chat only")
            note("YouTube: showing Top chat, because its menu didn't offer Live chat. Top chat holds some messages back.")
        failures = 0
        while streaming.is_set() and failures < 6:
            try:
                result = await asyncio.to_thread(yt_poll, chat)
            except (requests.RequestException, ValueError, KeyError) as error:
                skipped("youtube", error, "couldn't read the chat")
                failures += 1
                await asyncio.sleep(5)
                continue
            if result is None:
                break
            failures = 0
            for e in result[0]:
                if e["type"] == "delete":
                    send(e)
                elif e["id"] not in seen:
                    seen.append(e["id"])
                    if e["usec"] / 1e6 >= state["since"] - 30:     # nothing from before this stream
                        publish("youtube", e["name"], e["text"], "", e["badges"], e["id"], e["kind"], raw=e["id"][3:], uid=e.get("uid", ""),
                                alert=e.get("alert", ""), amount=e.get("amount", ""), system=e.get("system", ""))
            await asyncio.sleep(result[1])
        state["youtube_video"], state["youtube_chat"] = "", None
        set_status("youtube", "retry" if streaming.is_set() else "off")
        await asyncio.sleep(5)


# ---- Kick: its public chat feed (Pusher) ----------------------------------------------------------
def kick_alert(event, d):
    """(name, text, alert, amount) for Kick's subscription, gifted-subscription and host (raid) events."""
    if event.endswith("GiftedSubscriptionsEvent"):
        name, count = d.get("gifter_username") or "Someone", len(d.get("gifted_usernames") or [])
        return name, "%s gifted %d sub%s" % (name, count, "" if count == 1 else "s"), "gift", gifts(str(count), "sub")
    if event.endswith("StreamHostEvent"):
        name, count = d.get("host_username") or "Someone", str(d.get("number_viewers") or 0)
        return name, "%s is raiding with %s viewers" % (name, count), "raid", count
    name, months = d.get("username") or "Someone", str(d.get("months") or 1)
    if months.isdigit() and int(months) > 1:
        return name, "%s subscribed for %s months" % (name, months), "resub", months
    return name, "%s subscribed" % name, "sub", ""


KICK_PUSHER = ("34bf7a0ff419a2a775b9", "us2")     # Kick's public chat app on Pusher: its key and cluster, as last seen


def kick_feed(channel_id):
    """The address of Kick's public chat feed. Kick changes its Pusher key now and then, and its own web chat asks for
    the current one; CrossChat asks the same way (signed out, with a random client id), else uses the last one seen."""
    key, cluster = KICK_PUSHER
    if channel_id:
        try:
            reply = requests.post("https://web.kick.com/api/v1/realtime/channels/%d/chat/connection" % int(channel_id),
                                  headers=UA, timeout=12, json={"client": {"id": str(uuid.uuid4()), "type": "web"},
                                                                "capabilities": {"accepted_providers": [{"provider": "pusher"}]}})
            for link in (reply.json().get("data") or {}).get("connections") or []:
                given = link.get("credentials") or {}
                if (link.get("provider") == "pusher" and re.fullmatch(r"[0-9a-f]{16,40}", str(given.get("app_key", "")))
                        and re.fullmatch(r"[a-z0-9-]{2,20}", str(given.get("cluster", "")))):
                    key, cluster = given["app_key"], given["cluster"]
                    break
        except (requests.RequestException, ValueError, AttributeError, TypeError) as error:
            skipped("kick", error, "couldn't ask for the chat feed's address")
    return "wss://ws-%s.pusher.com/app/%s?protocol=7&client=js&version=8.4.0&flash=false" % (cluster, key)


async def kick(slug, room):
    channel_id = 0
    while True:                                   # the channel and chat room numbers come from the channel's public record
        try:
            found = await asyncio.to_thread(requests.get, "https://kick.com/api/v2/channels/" + slug, headers=UA, timeout=12)
            if found.status_code != 200:
                skipped("kick", ValueError("HTTP %d" % found.status_code), "couldn't read the channel's record")
            record = found.json() if found.status_code == 200 else {}
            room = room or int((record.get("chatroom") or {}).get("id", 0) or 0)
            channel_id = int(record.get("id") or 0)
        except (requests.RequestException, ValueError, AttributeError, TypeError) as error:
            skipped("kick", error, "couldn't read the channel's record")
        if room:
            break
        set_status("kick", "retry")
        await asyncio.sleep(60)
    wait = 2
    while True:
        try:
            set_status("kick", "waiting")
            url = await asyncio.to_thread(kick_feed, channel_id)    # asked again on every reconnect
            async with connect(url, open_timeout=20, ping_interval=None) as ws:
                await ws.send(json.dumps({"event": "pusher:subscribe", "data": {"auth": "", "channel": "chatrooms.%d.v2" % room}}))
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), 100)
                    except asyncio.TimeoutError:
                        await ws.send('{"event":"pusher:ping","data":{}}')
                        continue
                    try:
                        msg = json.loads(raw)
                        event = msg.get("event", "")
                        if event == "pusher_internal:subscription_succeeded":
                            set_status("kick", "on")
                            wait = 2
                        elif event == "pusher:ping":
                            await ws.send('{"event":"pusher:pong","data":{}}')
                        elif event.endswith("ChatMessageEvent"):
                            d = json.loads(msg["data"])
                            sender = d.get("sender") or {}
                            ident = sender.get("identity") or {}
                            text = re.sub(r"\[emote:\d+:([^\]]+)\]", r":\1:", d.get("content", ""))
                            publish("kick", sender.get("username", ""), text, ident.get("color", ""),
                                    [b.get("type", "") for b in ident.get("badges", [])], "kk-" + str(d.get("id", "")),
                                    raw=str(d.get("id", "")), uid=str(sender.get("id", "")))
                        elif event.endswith("MessageDeletedEvent"):
                            d = json.loads(msg["data"])
                            send({"type": "delete", "id": "kk-" + str((d.get("message") or {}).get("id", ""))})
                        elif event.endswith(("SubscriptionEvent", "GiftedSubscriptionsEvent", "StreamHostEvent")):
                            name, system, alert, amount = kick_alert(event, json.loads(msg["data"]))
                            publish("kick", name, "", kind="event", alert=alert, amount=amount, system=system)
                    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
                        skipped("kick", error)
        except Exception as error:        # any drop: wait and reconnect (Kick's reason, such as a key it no longer uses, logged)
            log.info("kick chat dropped (%s: %s); connecting again", type(error).__name__, str(error)[:160])
        set_status("kick", "retry")
        await asyncio.sleep(wait)
        wait = min(wait * 2, 60)


# ---- how many people are watching, per platform -----------------------------------------------------
def twitch_viewers(channel_name):
    """Twitch's own public web query; decapi.me (a free lookup service) is the fallback."""
    try:
        r = requests.post("https://gql.twitch.tv/gql", headers={"Client-ID": "kimne78kx3ncx6brgo4mv6wki5h1ko"}, timeout=10,
                          json={"query": "query($l:String!){user(login:$l){stream{viewersCount}}}", "variables": {"l": channel_name}}).json()
        stream = ((r.get("data") or {}).get("user") or {}).get("stream")
        return stream["viewersCount"] if stream else None
    except (requests.RequestException, ValueError, KeyError, TypeError):
        text = requests.get("https://decapi.me/twitch/viewercount/" + channel_name, timeout=10).text.strip()
        return int(text) if text.isdigit() else None


def youtube_viewers():
    chat, video = state["youtube_chat"], state["youtube_video"]
    if not (chat and video):
        return None
    r = web.post("https://www.youtube.com/youtubei/v1/updated_metadata?prettyPrint=false&key=" + chat["key"], timeout=10,
                 json={"context": {"client": {"clientName": "WEB", "clientVersion": chat["version"], "hl": "en"}}, "videoId": video}).json()
    for action in r.get("actions", []):
        count = ((action.get("updateViewershipAction") or {}).get("viewCount") or {}).get("videoViewCountRenderer")
        if count:
            digits = count.get("originalViewCount") or re.sub(r"\D", "", yt_text(count.get("viewCount")))
            return int(digits) if str(digits).isdigit() else None
    return None


def kick_viewers(slug):
    r = requests.get("https://kick.com/api/v2/channels/" + slug, headers=UA, timeout=10)
    live = r.json().get("livestream") if r.status_code == 200 else None
    return live.get("viewer_count") if live else None


TEST_VIEWERS = {"twitch": 128, "youtube": 342, "kick": 41, "x": 87, "tiktok": 263, "facebook": 57, "instagram": 96, "rumble": 38}
TEST_VIEWERS_SECONDS = 8
test_viewers_until = 0                       # while the viewer counter's test runs: the regular count updates mustn't cut it short


def viewer_event():
    if time.monotonic() < test_viewers_until:
        return {"type": "viewers", "counts": dict(TEST_VIEWERS), "total": sum(TEST_VIEWERS.values()), "test": True}
    return {"type": "viewers", "counts": dict(viewers), "total": sum(v for v in viewers.values() if v)}


async def audience():
    sources = [(name, job) for name, wanted, job in (("twitch", TWITCH, lambda: twitch_viewers(TWITCH)),
               ("youtube", YOUTUBE, youtube_viewers), ("kick", KICK, lambda: kick_viewers(KICK))) if wanted]
    while True:
        await streaming.wait()
        fresh = time.time() - state["since"] < 120
        for name, job in sources:
            try:
                count = await asyncio.to_thread(job)
                viewers[name] = int(count) if str(count).isdigit() else None     # whatever else an API answers: unknown
            except Exception as error:          # a failed lookup just shows as unknown
                viewers[name] = None
                skipped(name, error, "couldn't read the viewer count")
        send(viewer_event())
        await asyncio.sleep(10 if fresh else 30)


# ---- the windows: plain browser windows parked at the edge of the screen ---------------------------
if not (MAC or LINUX):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass


def browser_windows(prefix=None):
    if MAC:
        return macos.windows(browser_exe(), prefix) or []
    if LINUX:
        return linux.windows(browser_exe(), prefix) or []
    out = []

    def each(hwnd, _):
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value == "Chrome_WidgetWin_1" and user32.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, 256)
            if prefix is None or title.value.startswith(prefix):
                out.append(hwnd)
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(each), 0)
    return out


def place(hwnd, x, y, width, height):
    """Put the visible edges of a window exactly on a rectangle, without giving it the keyboard."""
    if MAC:
        return macos.place(hwnd, x, y, width, height)
    if LINUX:
        return linux.place(hwnd, x, y, width, height)
    outer, frame = wintypes.RECT(), wintypes.RECT()
    user32.ShowWindow(wintypes.HWND(hwnd), 4)
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(outer))
    if ctypes.WinDLL("dwmapi").DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(frame), ctypes.sizeof(frame)) != 0:
        frame = outer
    left, top = frame.left - outer.left, frame.top - outer.top
    right, bottom = outer.right - frame.right, outer.bottom - frame.bottom
    user32.SetWindowPos(wintypes.HWND(hwnd), None, x - left, y - top, width + left + right, height + top + bottom, 0x0004 | 0x0010)


def work_area():
    """The main screen without the taskbar: (left, top, right, bottom)."""
    if MAC:
        return macos.work_area()
    if LINUX:
        return linux.work_area()
    area = wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0)      # SPI_GETWORKAREA
    return area.left, area.top, area.right, area.bottom


def box(setting, part):
    """(x, y, width, height) for the chat window (part "chat") or a platform's page (part "x", "tiktok" and so on): the
    setting when it is a rectangle, else a strip at the right edge of the main screen, the chat on top and those pages
    under it."""
    if isinstance(setting, dict) and all(isinstance(setting.get(k), int) for k in ("x", "y", "width", "height")):
        return setting["x"], setting["y"], setting["width"], setting["height"]
    left, top, right, bottom = work_area()
    width = min(460, max(320, (right - left) // 4))
    pages = [name for name, on in (("x", X), ("tiktok", TIKTOK), ("facebook", FACEBOOK), ("instagram", INSTAGRAM), ("rumble", RB and RB.on()))
             if on]
    split = top + (bottom - top) * 3 // 5 if pages else bottom
    if part == "chat":
        return right - width, top, width, split - top
    height = (bottom - split) // max(1, len(pages))
    return right - width, split + height * (pages.index(part) if part in pages else 0), width, height


def browser_exe():
    """The browser the windows open in: "browser" in config.json is "auto" (Chrome, else Edge), "chrome", "edge" or a path.

    It has to be the everyday browser, because that is where the logins and the CrossChat extension live.
    """
    want = str(CFG.get("browser") or "auto")
    if MAC:
        return macos.browser(want)
    if LINUX:
        return linux.browser(want)
    if os.path.isfile(want):
        return want
    places = {"chrome": [r"%ProgramFiles%\Google\Chrome\Application\chrome.exe", r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
                         r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"],
              "edge": [r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe", r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"]}
    for name in (["chrome", "edge"] if want == "auto" else [want.lower()]):
        for path in places.get(name, []):
            path = os.path.expandvars(path)
            if os.path.exists(path):
                return path
    return None


# CrossChat's windows are the chat window and the platform pages it works through (PAGES: X Live Studio, your TikTok
# LIVE page, Live Producer, Instagram, Rumble's chat), opened in the everyday browser with --app. With the CrossChat
# extension in that browser (a chat window with it is connected: the "executor"), the extension places, moves and
# closes them with the browser's own window API (extension/windows.js), with no permission from the system: macOS
# refuses Apple Events to programs OBS starts, and Wayland lets no program move another's windows, so on a Mac and on
# Linux it does the placing. On Windows the system's own way places a window it can see: it puts the window's visible
# edges exactly on the place, in Windows' own pixels, while the browser's bounds include Windows' invisible resize
# borders (the visible window was 7 px in from them at the left, right and bottom, on GitHub's Windows machines) and
# are in the browser's own units. Closing is the extension's everywhere (it never closes an ordinary browser window of
# yours, even one showing the chat in a tab). Without the extension, or when it can't, the system's way does it all.
PAGES = ("x", "tiktok", "facebook", "instagram", "rumble")
WINDOW_WAIT = 30                             # seconds a new window may take to show up (a browser starting cold took 10 s in our tests)
HANDLE_WAIT = 5                              # once the extension has placed a window: seconds the system may take to find it too
pages = {}                                   # role -> {"url": address opened, "id": the browser's id for the window, "handle": the system's}
one_window = asyncio.Lock()                  # one opens at a time: the system's way knows a new window by its not having been there before


def system_places():
    """Whether the system's own way places a window it can see before the extension is asked (Windows)."""
    return not (MAC or LINUX)


async def by_extension(action, role, url="", where=None, window=None, known=None, wait=0):
    """A window job for the CrossChat extension, through the chat window that has it: "list" (the ids of the browser's
    windows), "place", "find" (a page just opened, not moved) or "close" one of CrossChat's windows. Its answer,
    {"ok": True, ...} when it did the job; ok is False when no chat window with the extension is connected, the
    extension is too old for window jobs, or it couldn't (then the system's way is next)."""
    if state["executor"] is None:
        return {"ok": False, "why": NO_EXECUTOR}
    job = {"id": secrets.token_hex(8), "kind": "window", "action": action, "role": role, "url": url,
           "box": [int(n) for n in where] if where else None, "window": window or 0, "known": known or [], "wait": wait}
    answer = await by_executor(job, wait + 15)
    if not isinstance(answer, dict):
        answer = {"ok": False, "why": "the extension did not answer"}
    if answer.get("ok") is True:
        if action != "list":
            log.info("window %s %s: done by the extension", action, role)
        return answer
    log.info("window %s %s: %s", action, role or "-", answer.get("why") or "it couldn't")
    return {**answer, "ok": False}


async def open_app(url, where, role=None):
    """Open a bare window of the everyday browser on `url` and put it at `where` (x, y, width, height), without taking the
    keyboard. A browser that is already running opens it where it likes (it takes --window-position and --window-size
    only when it starts with that window), so the window is moved once it is there. A platform page (`role`) is found
    by the extension too, when a chat window with it is connected, so the extension can close it later. Returns the
    system's handle for the window (or None), for closing it the system's way."""
    exe = browser_exe()
    if not exe:
        warn("CrossChat could not find Chrome or Edge. Set \"browser\" in config.json to the full path of your browser.")
        return None
    async with one_window:
        known = await by_extension("list", "") if role else {"ok": False}
        found = {}
        if not known["ok"]:
            handle = await os_open(exe, url, where, True)
        elif system_places():                    # Windows: the system places it; the extension finds it (to close it)
            native = asyncio.ensure_future(os_open(exe, url, where, True))
            found = await by_extension("find", role, url=url, known=known.get("windows"), wait=WINDOW_WAIT)
            handle = await native
            if not handle and found["ok"]:       # (the system didn't see it: the extension places it)
                await by_extension("place", role, url=url, where=where, window=found["window"])
        else:                                    # macOS, Linux: the extension finds and places it; the system finds its handle
            native = asyncio.ensure_future(os_open(exe, url, where, False))
            found = await by_extension("place", role, url=url, where=where, known=known.get("windows"), wait=WINDOW_WAIT)
            if found["ok"]:                      # placed: the system's handle (to close it without the extension) if it's there soon
                await asyncio.wait({native}, timeout=HANDLE_WAIT)
                if not native.done():
                    native.cancel()
                handle = native.result() if native.done() and not native.cancelled() else None
            else:
                handle = await native
                if handle:
                    place(handle, *where)
        if role:
            pages[role] = {"url": url, "id": found.get("window") if found.get("ok") else None, "handle": handle}
        return handle


async def os_open(exe, url, where, place_it):
    """Start the window with the browser's command line, then find it (and with `place_it`, place it) the system's way."""
    if MAC:
        return await macos.open_app(exe, url, where, place_it, WINDOW_WAIT)
    if LINUX:
        return await linux.open_app(exe, url, where, place_it, WINDOW_WAIT)
    before, front = set(browser_windows()), user32.GetForegroundWindow()
    cmd = [exe, "--app=" + url, "--window-position=%d,%d" % where[:2], "--window-size=%d,%d" % where[2:]]
    subprocess.Popen(cmd, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + WINDOW_WAIT
    while time.monotonic() < deadline:
        await asyncio.sleep(0.25)
        new = [h for h in browser_windows() if h not in before]
        if new:
            if place_it:
                place(new[0], *where)
            if front:
                user32.SetForegroundWindow(front)
            return new[0]
    return None


async def show_window():
    """Open the chat window, or put the open one back in its place."""
    where = box(CFG["window"], "chat")
    if system_places():                          # Windows: its own way, when it sees the chat window
        found = browser_windows(TITLE)
        if found:
            place(found[0], *where)
            return
    moved = await by_extension("place", "chat", where=where)
    if moved["ok"]:
        return
    if moved.get("none") or system_places():    # (the extension sees every window of its browser: no chat window there)
        found = []
    elif LINUX:
        found = await asyncio.to_thread(linux.windows, browser_exe(), TITLE)
        if found is None and roles["speaker"]:   # open already, where X can't see it (a Wayland browser): not a second one
            return
    else:
        found = await asyncio.to_thread(browser_windows, TITLE)     # (a Mac asks the browser)
    if found:
        place(found[0], *where)
        return
    state["chat_opened"] = (where, time.time())  # the extension puts it in its place once it's up (chat_connected)
    settled = state["chat_settled"] = asyncio.Event()
    try:
        if await open_app("http://127.0.0.1:%d/" % PORT, where) and system_places():
            state.pop("chat_opened", None)       # (Windows: placed already, the system's way)
    finally:
        settled.set()


async def chat_connected():
    """A chat window with the extension has connected. If CrossChat has just opened it and the system's way didn't
    place it, the extension puts it in its place (a running browser opens a new window where it likes)."""
    opened = state.get("chat_opened")
    if not opened or time.time() - opened[1] >= 2 * WINDOW_WAIT:
        return
    if "chat_settled" in state:                  # (the system's way may be finding it this moment)
        await state["chat_settled"].wait()
    if state.pop("chat_opened", None):
        await by_extension("place", "chat", where=opened[0])


async def open_page(role, url, where):
    """Open one of the platform pages in a window of its own, closing the one opened before."""
    await close_page(role)
    await open_app(url, where, role)


async def close_page(role):
    """Close the platform page CrossChat opened for `role`, if it is still there: by the extension, else the system's way."""
    page = pages.pop(role, None)
    if page and not (await by_extension("close", role, url=page["url"], window=page.get("id")))["ok"]:
        close_handle(page.get("handle"))


async def close_chat():
    """Close the chat window: by the extension (every chat window CrossChat opened in that browser), else the system's way."""
    state.pop("chat_opened", None)
    if not (await by_extension("close", "chat"))["ok"]:
        close_window()


async def close_windows():
    """The platform pages, then the chat window (it carries the extension's jobs, so it goes last)."""
    for role in PAGES:
        await close_page(role)
    await close_chat()


def close_window():
    if MAC:
        return macos.close_titled(browser_exe(), TITLE)
    if LINUX:
        return linux.close_titled(browser_exe(), TITLE)
    for hwnd in browser_windows(TITLE):
        close_handle(hwnd)


def close_handle(hwnd):
    """Close a browser window CrossChat opened, if it is still there."""
    if MAC:
        macos.close(hwnd)
    elif LINUX:
        linux.close(hwnd)
    elif hwnd and user32.IsWindow(wintypes.HWND(hwnd)):
        user32.PostMessageW(wintypes.HWND(hwnd), 0x0010, 0, 0)


# ---- X: a livestream there has to be started on X's own page -----------------------------------------
# The CrossChat extension does the clicks. It only acts when this hub has just asked for it ("armed" below), so a
# bookmark or a reload of that page can never start a stream by itself.
def x_title():
    """Title for the X livestream: the first line of "title_file" (after "title_prefix") when that file has one, else "title"."""
    line = ""
    if X.get("title_file"):
        try:
            with open(os.path.expandvars(X["title_file"]), encoding="utf-8-sig") as f:
                line = f.read().strip().split("\n")[0].strip()
        except OSError:
            line = ""
    return ((X.get("title_prefix") or "") + line)[:120] if line else (X.get("title") or "Live now")[:120]


async def x_go(mode):
    """Open X's Live Studio and ask the extension to go live there.

    mode: "live" (public), "private" (only the account owner can watch: for testing) or "dry" (fill the
    form, never press Go Live). "live" is refused unless OBS is really streaming to the outside.
    """
    if not X:
        return "X is switched off in config.json"
    if mode == "live" and not (streaming.is_set() and not state.get("local")):
        mode = ""
    tail = {"live": "#golive", "private": "#golive-private", "dry": "#golive-dry"}.get(mode, "")
    state["x_armed"] = (mode, time.time()) if tail else None
    await open_page("x", "https://studio.x.com/live" + tail, box(X.get("window"), "x"))
    if mode == "live":
        note("X: starting the livestream there...")
    return mode or "The stream is not live, so X was only opened"


x_told = collections.deque(maxlen=3000)      # X chat lines already shown (its page reports them again after a reload)


def x_off():
    if status.get("x") == "on":
        viewers.pop("x", None)
        set_status("x", "off")
        send(viewer_event())


def x_feed(first):
    """The extension passes on what X's livestream page shows: viewer count and new chat lines."""
    if first("over"):
        x_off()
        return
    state["x_seen"] = time.time()
    set_status("x", "on")
    if first("viewers").isdigit() and viewers.get("x") != int(first("viewers")):
        viewers["x"] = int(first("viewers"))
        send(viewer_event())
    mid = "x-" + re.sub(r"\W", "", first("id"))[:80]
    if first("text") and mid not in x_told:
        x_told.append(mid)
        publish("x", first("name")[:60], first("text")[:300], mid=mid, handle=re.sub(r"\W", "", first("handle"))[:30])


# A page in a covered window has its timers throttled by Chrome, to once a minute after five minutes hidden: a page counts
# as gone only after going quiet for longer than that.
PAGE_QUIET = 90


async def x_watch():
    """X, TikTok, Facebook and Instagram count as live only while their pages keep reporting in."""
    while True:
        await asyncio.sleep(5)
        if X and time.time() - state.get("x_seen", 0) > PAGE_QUIET:
            x_off()
        for chat in PAGE_CHATS:
            if chat.wanted() and status.get(chat.name) == "on" and time.time() - state.get(chat.name + "_seen", 0) > PAGE_QUIET:
                chat.off()
                if streaming.is_set():
                    note(chat.stopped)


def x_result(ok, mode, step):
    log.info("X %s: %s (%s)", mode, "ok" if ok else "stopped", step)
    if mode == "end":
        state["x_end"] = False
        if ok:
            x_off()
        note("X: livestream ended." if ok else "X: could not end the livestream there (%s). End it on the X page." % step)
    elif mode == "live":
        note("X: live." if ok else "X: could not go live (stopped at: %s). Use Go live on X to try again, or finish on the X page." % step)
    else:
        note("X test (%s): %s" % (mode, "worked" if ok else "stopped at: " + step))


# ---- chat read off a platform's own page: one class for TikTok, Facebook and Instagram ---------------------------
class PageChat:
    """A platform whose chat comes from its own page in the streamer's browser, passed on by the extension: the page opens
    when the stream starts, and the platform counts as live only while the page keeps reporting in (x_watch).

    wanted says whether it is switched on, address gives the page, stopped is what to say when the page goes quiet. A
    line's id is kept after prefix, without id_junk and at most id_most long; moderated: it doubles as the id to moderate by."""

    def __init__(self, name, wanted, address, stopped, prefix, id_junk=r"\W", id_most=80, moderated=False):
        self.name, self.wanted, self.address, self.stopped = name, wanted, address, stopped
        self.prefix, self.id_junk, self.id_most, self.moderated = prefix, id_junk, id_most, moderated
        self.told = collections.deque(maxlen=5000)      # lines already shown (a page shows them again after a reload)

    async def open(self):
        set_status(self.name, "waiting")
        await open_page(self.name, self.address(), box(CFG.get(self.name + "_window"), self.name))

    def off(self):
        if status.get(self.name) in ("on", "waiting"):
            viewers.pop(self.name, None)
            set_status(self.name, "off")
            send(viewer_event())

    def mine(self, first):
        """Whether the page that reported counts (anything from another page is ignored)."""
        return bool(self.wanted())

    def feed(self, first):
        """The extension passes on what the page shows: new lines and the viewer count. Answers whether the page counts."""
        if not self.mine(first):
            return False
        if first("over"):
            self.off()
            return True
        state[self.name + "_seen"] = time.time()
        set_status(self.name, "on")
        if first("viewers").isdigit() and viewers.get(self.name) != int(first("viewers")):
            viewers[self.name] = int(first("viewers"))
            send(viewer_event())
        try:
            lines = json.loads(first("lines") or "[]")
        except ValueError:
            lines = []
        for line in lines[:50] if isinstance(lines, list) else []:
            if isinstance(line, dict):
                self.take(line)
        return True

    def take(self, line):
        mid = self.prefix + re.sub(self.id_junk, "", str(line.get("id", "")))[:self.id_most]
        name, text = " ".join(str(line.get("name", "")).split())[:60], " ".join(str(line.get("text", "")).split())[:1000]
        if name and text and mid != self.prefix and mid not in self.told:
            self.told.append(mid)
            publish(self.name, name, text, badges=["broadcaster"] if line.get("host") is True else [], mid=mid, raw=mid if self.moderated else "")


# ---- TikTok LIVE: chat from the streamer's own LIVE page, through the extension ---------------------------
# TikTok has no public chat API, and the unofficial ones send the streamer's TikTok session to an outside signing
# service. CrossChat doesn't: when OBS goes live it opens the streamer's own LIVE page in their everyday browser, and
# the extension passes on the chat lines shown there and types replies into TikTok's own chat box. On any other
# TikTok page (someone else's LIVE, say) it reads nothing.
tiktok_likes = {}                            # viewer -> likes not shown yet: one alert per viewer per burst of likes
tiktok_once = {}                             # (kind, viewer) -> when last shown: a follow once a stream, a share once a minute
TIKTOK_EVENTS = ("gift", "follow", "share", "like", "join")
TIKTOK_AGAIN = {"follow": float("inf"), "share": 60, "join": 600}       # seconds before the same viewer's shows again
TIKTOK_SAYS = {"follow": "%s followed", "share": "%s shared the LIVE", "join": "%s joined"}
LIKE_QUIET, LIKE_LONGEST = 15, 120           # a viewer's likes show once they stop for this long, or after this long at most
LIKE_ONE_BY_ONE = 3                          # more viewers' likes due at once than this: one line for all of them


def tiktok_page():
    return "https://www.tiktok.com/@%s/live" % TIKTOK


class TikTokChat(PageChat):
    """TikTok's page also shows gifts, follows, shares, likes and joins (its lines have no ids of their own; see
    tiktok.js), and on any TikTok page but the streamer's own LIVE nothing counts."""

    def mine(self, first):
        return bool(TIKTOK) and first("page").lower().lstrip("@") == TIKTOK

    def off(self):
        if status.get(self.name) in ("on", "waiting"):
            tiktok_flush_likes(time.time(), everything=True)
        super().off()

    def feed(self, first):
        mine = super().feed(first)
        if mine and not first("over"):
            tiktok_flush_likes(time.time())
        return mine

    def take(self, line):
        mid = "tt-" + re.sub(r"\W", "", str(line.get("id", "")))[:80]
        name, text = " ".join(str(line.get("name", "")).split())[:60], " ".join(str(line.get("text", "")).split())[:300]
        kind = line.get("kind") or "chat"
        if not name or mid == "tt-" or mid in self.told:
            return
        if kind == "chat" and text:
            self.told.append(mid)
            publish("tiktok", name, text, badges=["broadcaster"] if line.get("host") is True else [], mid=mid)
        elif kind in TIKTOK_EVENTS and line.get("host") is not True:
            self.told.append(mid)
            tiktok_event(kind, name, line, mid)


def tiktok_event(kind, name, line, mid):
    """A gift, follow, share, like or join that the streamer's TikTok LIVE page showed, as an alert. TikTok's page
    gives a gift's name and how many were sent, not what they cost, so no money value is made up for them."""
    now = time.time()
    count = line.get("count")
    count = count if isinstance(count, int) and 0 < count < 100000 else 1
    if kind == "gift":
        gift = " ".join(str(line.get("gift", "")).split())[:40] or "a gift"
        amount = gift if count == 1 else "%s ×%d" % (gift, count)
        publish("tiktok", name, "", kind="event", alert="gift", amount=amount, system="%s sent %s" % (name, amount), mid=mid)
    elif kind == "like":
        tally = tiktok_likes.setdefault(name.lower(), {"name": name, "likes": 0, "first": now, "last": now})
        tally["likes"] += count
        tally["last"] = now
        if len(tiktok_likes) > 2000:             # a huge LIVE: show the oldest tallies now rather than keep them all
            tiktok_flush_likes(now, oldest=len(tiktok_likes) - 2000)
    elif kind != "join" or FILTERS.get("joins"):
        key = (kind, name.lower())
        if now - tiktok_once.get(key, float("-inf")) < TIKTOK_AGAIN[kind]:
            return
        tiktok_once[key] = now
        if len(tiktok_once) > 20000:
            tiktok_once.pop(next(iter(tiktok_once)))
        publish("tiktok", name, "", kind="event", alert=kind, mid=mid, system=TIKTOK_SAYS[kind] % name)


def tiktok_flush_likes(now, everything=False, oldest=0):
    """Show each viewer's likes as one alert once they've stopped liking for a bit (or liked for a long while). When
    many are due at once (a busy LIVE), they show as one line ("12 viewers liked the LIVE ×340") instead."""
    due = []
    for key, tally in sorted(tiktok_likes.items(), key=lambda kv: kv[1]["first"]):
        if everything or oldest > 0 or now - tally["last"] >= LIKE_QUIET or now - tally["first"] >= LIKE_LONGEST:
            del tiktok_likes[key]
            oldest -= 1
            due.append(tally)
    if len(due) > LIKE_ONE_BY_ONE:
        due = [{"name": "%d viewers" % len(due), "likes": sum(t["likes"] for t in due), "first": now}]
    for tally in due:
        n, who = tally["likes"], tally["name"]
        publish("tiktok", who, "", kind="event", alert="like", amount=str(n), system="%s liked the LIVE ×%d" % (who, n),
                mid="tt-like-%s" % hashlib.sha256(("%s\n%f" % (who.lower(), tally["first"])).encode()).hexdigest()[:16])


tiktok_chat = TikTokChat("tiktok", lambda: TIKTOK, tiktok_page,
                         "TikTok: its LIVE page stopped reporting (closed, or the LIVE ended). TikTok chat is paused.", "tt-")


# ---- Facebook Live and Instagram Live: comments from their own Live producers, through the extension ---------------------
# Live Producer is where a Facebook live is started and ended, and it only ever shows the signed-in streamer's own
# broadcasts; Instagram's Live producer (Create → Live video on instagram.com) is the same for a live from OBS. When OBS
# goes live, CrossChat opens them; the extension passes on the comments shown there and types replies into their comment
# boxes. Nothing else on Facebook or Instagram is read.
facebook_chat = PageChat("facebook", lambda: FACEBOOK, lambda: "https://www.facebook.com/live/producer",
                         "Facebook: Live Producer stopped reporting (closed, or the live ended). Facebook comments are paused.",
                         "fb-", id_junk=r"[^\w=-]", id_most=120, moderated=True)
instagram_chat = PageChat("instagram", lambda: INSTAGRAM, lambda: "https://www.instagram.com/",
                          "Instagram: its Live producer stopped reporting (closed, or the live ended). Instagram comments are paused.", "ig-")
PAGE_CHATS = (tiktok_chat, facebook_chat, instagram_chat)
PAGE_FEEDS = {"/%s/feed" % chat.name: chat for chat in PAGE_CHATS}
tiktok_feed, tiktok_off, tiktok_told = tiktok_chat.feed, tiktok_chat.off, tiktok_chat.told
facebook_feed, facebook_told = facebook_chat.feed, facebook_chat.told
instagram_feed, instagram_told = instagram_chat.feed, instagram_chat.told


# ---- Rumble: its official Live Stream API (read only) ----------------------------------------------------
def rumble_time(text):
    """Rumble's ISO 8601 times as seconds since 1970, or 0."""
    try:
        return datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0


def rumble_chat_id(live):
    """The number of the live's Rumble chat (its pop-out is rumble.com/chat/popup/<number>): the API gives the
    livestream's id in base 36."""
    raw = str(live.get("id") or "").lower()
    return str(int(raw, 36)) if re.fullmatch(r"[0-9a-z]{1,13}", raw) else ""


async def rumble_open(chat):
    """Rumble's own chat pop-out for this live, where the extension types replies (Rumble has no API for sending)."""
    await open_page("rumble", "https://rumble.com/chat/popup/" + chat, box(CFG.get("rumble_window"), "rumble"))


def rumble_read(data, told, last):
    """One answer from Rumble: chat lines, Rants and subs since the stream started, and the viewer count."""
    live = next((s for s in data.get("livestreams") or [] if isinstance(s, dict) and s.get("is_live")), None)
    if not live:
        if status.get("rumble") == "on":
            viewers.pop("rumble", None)
            set_status("rumble", "waiting")
            send(viewer_event())
        state["rumble_chat"] = ""
        return
    set_status("rumble", "on")
    chat_id = rumble_chat_id(live)
    if chat_id and chat_id != state.get("rumble_chat"):
        state["rumble_chat"] = chat_id
        if not state.get("local") and not TEST:
            spawn(rumble_open(chat_id))
    if str(live.get("watching_now", "")).isdigit() and viewers.get("rumble") != int(live["watching_now"]):
        viewers["rumble"] = int(live["watching_now"])
        send(viewer_event())
    since = state["since"] - 30
    chat = live.get("chat") or {}

    def new(kind, item, *key):
        mid = "rm-%s-%s" % (kind, hashlib.sha256("\n".join(str(k) for k in key).encode()).hexdigest()[:16])
        if mid in told or rumble_time(item.get("created_on") or item.get("subscribed_on")) < since:
            return ""
        told.append(mid)
        return mid

    for m in reversed(chat.get("recent_messages") or []):      # (newest first in Rumble's answer)
        if isinstance(m, dict) and m.get("username") and m.get("text"):
            mid = new("m", m, m["username"], m.get("created_on"), m["text"])
            if mid:
                badges = [b for b in m.get("badges") or [] if isinstance(b, str)][:6]
                publish("rumble", str(m["username"])[:60], " ".join(str(m["text"]).split())[:500], badges=badges, mid=mid, raw=mid)
    for r in reversed(chat.get("recent_rants") or []):
        if isinstance(r, dict) and r.get("username"):
            mid = new("r", r, r["username"], r.get("created_on"), r.get("text"))
            if mid:
                amount = "$%.2f" % (int(r.get("amount_cents") or 0) / 100)
                publish("rumble", str(r["username"])[:60], " ".join(str(r.get("text") or "").split())[:500], kind="event", alert="superchat",
                        amount=amount, system="%s sent a %s Rant" % (str(r["username"])[:60], amount), mid=mid)
    for sub in reversed((data.get("subscribers") or {}).get("recent_subscribers") or []):
        if isinstance(sub, dict) and sub.get("username"):
            mid = new("s", sub, sub["username"], sub.get("subscribed_on"))
            if mid:
                publish("rumble", str(sub["username"])[:60], "", kind="event", alert="sub", system="%s subscribed" % str(sub["username"])[:60], mid=mid)
    gifted = data.get("gifted_subs") or {}
    count = gifted.get("num_gifted_subs")
    if isinstance(count, int):
        if last.get("gifts") is not None and count > last["gifts"]:
            latest = gifted.get("latest_gifted_sub") or {}
            who, n = str(latest.get("purchased_by") or "Someone")[:60], int(latest.get("total_gifts") or count - last["gifts"])
            amount = gifts(str(n), "sub")
            publish("rumble", who, "", kind="event", alert="gift", amount=amount, system="%s gifted %s" % (who, amount), mid="rm-g-%d" % count)
        last["gifts"] = count


async def rumble_watch():
    """While OBS is live and Rumble is connected: ask Rumble every few seconds (its API answers with the latest 50)."""
    told, last, wait, warned = collections.deque(maxlen=3000), {}, 5, ""
    while True:
        await streaming.wait()
        if not (RB and RB.on()) or DEMO:
            await asyncio.sleep(10)
            continue
        if status.get("rumble") in (None, "off"):
            set_status("rumble", "waiting")
            last.clear()
        try:
            rumble_read(await asyncio.to_thread(RB.fetch), told, last)
            wait = 5
        except RumbleError:
            set_status("rumble", "retry")
            if RB.why and RB.why != warned:
                warned = RB.why
                note("Rumble: " + RB.why)
                send(rumble_event())
            wait = 60 if RB.why else min(wait * 2, 60)
        await asyncio.sleep(wait)


# ---- stream start and stop -------------------------------------------------------------------------
closing = None


async def stream_started(local=False):
    """local: OBS is sending its main stream to this PC only (a test), so nothing public should follow."""
    global closing
    if closing:
        closing.cancel()
        closing = None
    if streaming.is_set():
        return
    log.info("stream started%s", " (to this PC only)" if local else "")
    state["since"], state["local"], state["x_end"] = time.time(), local, False
    warned.clear()
    messages.clear()
    x_told.clear()
    tiktok_likes.clear()
    tiktok_once.clear()
    for chat in PAGE_CHATS:
        chat.told.clear()
    seen.clear()
    if LOG and not DEMO and (CFG.get("logs") or {}).get("enabled", True):
        name = LOG.start()
        if name:
            log.info("chat history: logs/%s.jsonl", name)
    streaming.set()
    send({"type": "clear"})
    send(status_event())
    note("Test stream to this PC only." if local else "Stream started. Chat from every platform shows up here.")
    if CFG.get("open_window_on_stream_start", True) and "--no-window" not in ARGV:
        await show_window()
    for chat in PAGE_CHATS:
        if chat.wanted() and not local and not TEST:
            spawn(chat.open())
    if DC and not local and not TEST:
        DC.live(live_notice())
    if X.get("auto_go_live") and not local and not TEST:
        async def soon():                       # give X a moment to see the video arriving
            await asyncio.sleep(X.get("delay_seconds", 12))
            if streaming.is_set():
                await x_go("live")
        spawn(soon())


async def stream_stopped():
    global closing
    if not streaming.is_set():
        return
    log.info("stream stopped")
    streaming.clear()
    if LOG:
        LOG.stop()
    for name in [n for n in viewers if n != "x"]:  # X keeps its own count until its livestream is over
        del viewers[name]
    send(status_event())
    send(viewer_event())
    note("Stream ended.")

    async def end_x():                           # a livestream still running on X is ended there too,
        await asyncio.sleep(X.get("end_seconds_after_obs", 15))      # unless OBS comes straight back
        if not streaming.is_set() and status.get("x") == "on":
            state["x_end"] = True
    if X.get("end_with_obs", True):
        spawn(end_x())

    async def later():
        await asyncio.sleep(CFG.get("close_window_seconds_after_stream", 120))
        for chat in PAGE_CHATS:
            chat.off()
        state["rumble_chat"] = ""
        await close_windows()
    closing = spawn(later())


# ---- OBS: its WebSocket server tells the hub when the stream starts and stops ----------------------
def obs_settings():
    """Where OBS's WebSocket server listens and its password: config.json's "obs" section first, else OBS's own
    settings (in the folder the OBS script passes with --obs-config, or the usual one under %APPDATA%, or
    ~/Library/Application Support on a Mac, or ~/.config on Linux)."""
    folder = arg("--obs-config", "") or (macos.OBS_SETTINGS if MAC else linux.OBS_SETTINGS if LINUX else os.path.expandvars(r"%APPDATA%\obs-studio"))
    try:
        with open(os.path.join(folder, "plugin_config", "obs-websocket", "config.json"), encoding="utf-8-sig") as f:
            theirs = json.load(f)
    except (OSError, ValueError):
        theirs = {}
    mine = CFG["obs"]
    return {"host": mine.get("host") or "127.0.0.1", "port": int(mine.get("port") or theirs.get("server_port") or 4455),
            "password": mine.get("password") or theirs.get("server_password") or "",
            "enabled": theirs.get("server_enabled", True) or bool(mine.get("port"))}


RETRY_AFTER_REFUSAL = 10                     # seconds before trying again after OBS refused the password


def obs_open(pid):
    """True while process `pid` (the OBS that started this hub) is running."""
    if MAC:
        return macos.running(pid)
    if LINUX:
        return linux.running(pid)
    handle = kernel32.OpenProcess(0x00100000, False, pid)          # SYNCHRONIZE
    if not handle:
        return False
    try:
        return kernel32.WaitForSingleObject(handle, 0) == 0x102     # WAIT_TIMEOUT: still running
    finally:
        kernel32.CloseHandle(handle)


def answer(hello, password):
    """The authentication string obs-websocket 5 asks for in its Hello."""
    secret = base64.b64encode(hashlib.sha256((password + hello["salt"]).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + hello["challenge"]).encode()).digest()).decode()


async def obs_session(ws, password):
    """One connection to OBS: say who we are, then follow its stream until the connection ends."""
    hello = json.loads(await ws.recv())["d"]
    ident = {"rpcVersion": 1, "eventSubscriptions": 64}        # 64 = output events
    if hello.get("authentication"):
        ident["authentication"] = answer(hello["authentication"], password)
    await ws.send(json.dumps({"op": 1, "d": ident}))
    if json.loads(await ws.recv()).get("op") != 2:                 # 2 = Identified
        return
    log.info("connected to OBS %s (obs-websocket %s)", hello.get("obsStudioVersion", "?"), hello.get("obsWebSocketVersion", "?"))
    await ws.send(json.dumps({"op": 6, "d": {"requestType": "GetStreamStatus", "requestId": "now"}}))
    where = json.dumps({"op": 6, "d": {"requestType": "GetStreamServiceSettings", "requestId": "where"}})
    async for raw in ws:
        d = json.loads(raw)["d"]
        if d.get("requestId") == "now":
            if (d.get("responseData") or {}).get("outputActive"):
                await ws.send(where)
            else:
                await stream_stopped()
        elif d.get("requestId") == "where":     # where the main stream goes decides whether this is a test
            server = ((d.get("responseData") or {}).get("streamServiceSettings") or {}).get("server", "")
            await stream_started(local=server.startswith(("rtmp://127.", "rtmp://localhost")))
        elif d.get("eventType") == "StreamStateChanged":
            phase = d["eventData"].get("outputState", "")
            if phase.endswith("_STARTED"):
                await ws.send(where)
            elif phase.endswith("_STOPPED"):
                await stream_stopped()


obs_gone = threading.Event()                 # --obs-stdin: OBS's end of our input has closed


def watch_stdin(fd):
    """--obs-stdin (OBS from Flathub, whose process id means nothing outside its sandbox): OBS holds the other end of
    this program's standard input, so it ends exactly when OBS does."""
    try:
        while os.read(fd, 4096):
            pass
    except OSError:
        pass
    obs_gone.set()


async def obs_link():
    """Follow OBS until it closes. With --obs-pid that is the OBS process ending (with --obs-stdin, our input ending);
    started by hand, it is the connection ending (or a minute and a half without one)."""
    pid = int(arg("--obs-pid", "0") or 0)
    if "--obs-stdin" in ARGV:
        obs_gone.clear()
        threading.Thread(target=watch_stdin, args=(0,), daemon=True).start()     # (0: standard input)
        following = lambda: not obs_gone.is_set()
    else:
        following = (lambda: obs_open(pid)) if pid else None
    tries, told = 0, set()
    while following() if following else tries < 30:
        where = obs_settings()
        try:
            ws = await connect("ws://%s:%d" % (where["host"], where["port"]), open_timeout=5, max_size=2 ** 24)
        except (OSError, asyncio.TimeoutError, InvalidHandshake):
            tries += 1
            if tries == 10 and "reach" not in told:
                told.add("reach")
                warn("CrossChat cannot reach OBS's WebSocket server at %s:%d. In OBS, open Tools > WebSocket Server Settings "
                     "and tick Enable WebSocket server." % (where["host"], where["port"]) if where["enabled"] else
                     "OBS's WebSocket server is switched off. In OBS, open Tools > WebSocket Server Settings and tick "
                     "Enable WebSocket server; CrossChat connects by itself once it is on.")
            await asyncio.sleep(3)
            continue
        tries = 0

        async def gone(link):                    # hang up as soon as that OBS closes (or another one could be followed)
            while following():
                await asyncio.sleep(2)
            await link.close()
        watcher = asyncio.create_task(gone(ws)) if following else None
        try:
            async with ws:
                await obs_session(ws, where["password"])
        except ConnectionClosed as closed:
            if closed.rcvd and closed.rcvd.code == 4009:                                 # AuthenticationFailed
                if "password" not in told:
                    told.add("password")
                    warn("OBS refused CrossChat's WebSocket password. Leave \"password\" in config.json empty so CrossChat "
                         "reads it from OBS, or copy it from Tools > WebSocket Server Settings > Show Connect Info.")
                await asyncio.sleep(RETRY_AFTER_REFUSAL)
        except (OSError, ValueError, KeyError) as error:
            log.warning("OBS connection: %s", error)
        finally:
            if watcher:
                watcher.cancel()
        if not following:
            break
        await asyncio.sleep(2)
    log.info("OBS closed")
    await close_windows()


# ---- other streaming apps: when OBS isn't the one streaming -------------------------------------------
# Streamlabs Desktop answers on this PC's own TCP port without a token (its Settings > Remote Control is only for other
# devices): JSON-RPC, one message per line. Its status is asked for every couple of seconds rather than subscribed to: a
# request that gets no answer (it is loading, or switching scene collection) is simply asked again next time.
STREAMLABS_PORT = 28194
STREAMLABS_POLL = 2                          # seconds between two questions, and how long one may take
STREAMLABS_RETRY = 3                         # seconds between two tries to reach it
STREAMLABS_GONE = 30                         # seconds without it before it counts as closed (changing its Remote Control settings drops us)
BROADCASTERS = ("auto", "obs", "streamlabs", "manual")


async def streamlabs_status(reader, writer, number):
    """Streamlabs' streamingStatus now (offline, starting, live, ending, reconnecting), or None when it doesn't say in time."""
    ask = {"jsonrpc": "2.0", "id": number, "method": "getModel", "params": {"resource": "StreamingService", "args": []}}
    writer.write((json.dumps(ask) + "\n").encode())
    await writer.drain()

    async def answer():
        while True:
            line = await reader.readline()
            if not line:
                raise ConnectionError("Streamlabs closed the connection")
            try:
                said = json.loads(line)
            except ValueError:
                continue
            if isinstance(said, dict) and said.get("id") == number:
                result = said.get("result")
                return result.get("streamingStatus") if isinstance(result, dict) else None
    try:
        return await asyncio.wait_for(answer(), STREAMLABS_POLL)
    except asyncio.TimeoutError:
        return None


async def streamlabs_session(reader, writer):
    """One connection to Streamlabs: follow its stream until the connection ends."""
    number = 0
    while True:
        number += 1
        status = await streamlabs_status(reader, writer, number)
        if status == "live":                     # "reconnecting" and "ending" are still the same stream
            await stream_started()
        elif status == "offline":
            await stream_stopped()
        await asyncio.sleep(STREAMLABS_POLL)


async def streamlabs_link():
    """Follow Streamlabs Desktop: wait for it for as long as it takes, and leave once it has closed."""
    gone, told = None, False
    while gone is None or time.monotonic() - gone < STREAMLABS_GONE:
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", STREAMLABS_PORT), 5)
        except (OSError, asyncio.TimeoutError):
            if not told:
                told = True
                log.info("waiting for Streamlabs Desktop")
            await asyncio.sleep(STREAMLABS_RETRY)
            continue
        log.info("connected to Streamlabs Desktop")
        told = False
        try:
            await streamlabs_session(reader, writer)
        except (OSError, ConnectionError) as error:
            log.info("Streamlabs connection: %s", error)
        finally:
            writer.close()
        gone = time.monotonic()
    log.info("Streamlabs Desktop closed")


async def streamlabs_answers():
    """True when a Streamlabs Desktop is running on this PC right now."""
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", STREAMLABS_PORT), 1)
    except (OSError, asyncio.TimeoutError):
        return False
    writer.close()
    return True


async def manual_link():
    """No streaming app to follow: the chat window's Start stream button (or control.py stream-start) says when you are live."""
    log.info("following no streaming app: Start stream in the chat window says when you are live")
    await asyncio.Event().wait()


async def manual_stream(go):
    """Start stream / End stream, when CrossChat follows no app. With an app, the app knows better."""
    if state.get("app") != "manual":
        return {"ok": False, "why": "CrossChat follows your streaming app, so it knows by itself when you are live."}
    if go == "start":
        await stream_started()
    elif go == "end":
        await stream_stopped()
    else:
        return {"ok": False, "why": "That is neither start nor end."}
    return {"ok": True, "live": streaming.is_set()}


def broadcaster():
    """The app config.json names; anything else is "auto"."""
    chosen = str(CFG.get("broadcaster") or "auto").strip().lower()
    return chosen if chosen in BROADCASTERS else "auto"


async def follow_app():
    """Follow the streaming app until it closes. "auto": the OBS that started this hub; started any other way, a
    Streamlabs that is already running, else OBS (as a hub started by hand always has)."""
    chosen = broadcaster()
    if chosen == "auto":
        by_obs = "--obs-pid" in ARGV or "--obs-stdin" in ARGV
        chosen = "streamlabs" if not by_obs and await streamlabs_answers() else "obs"
    state["app"], state["leave"] = chosen, None
    if chosen == "obs":
        await obs_link()
        return
    state["leave"] = asyncio.Event()             # "Close CrossChat": these two don't end when OBS closes
    link = asyncio.create_task(streamlabs_link() if chosen == "streamlabs" else manual_link())
    asked = asyncio.create_task(state["leave"].wait())
    await asyncio.wait({link, asked}, return_when=asyncio.FIRST_COMPLETED)
    asked.cancel()
    if link.done():
        link.result()                            # something unexpected goes up to keep_running, which starts it again
    else:
        link.cancel()
    await stream_stopped()
    await close_windows()


# ---- themes: how the on-stream widgets look ----------------------------------------------------------
# The ones that come with CrossChat are in hub/presets and can't be changed; yours are in themes/ in the CrossChat
# folder, one JSON file each, made in the Theme Studio (/studio).
THEME_MOST = 224 * 1024                      # bytes of a theme file (all nine custom logos fit); web/theme.js says the same


def themes_dir():
    return arg("--themes", os.path.join(HOME, "themes"))


def theme_path(name):
    """The file of theme `name` (a preset first), or None."""
    if not THEME_NAME.fullmatch(name or ""):
        return None
    for folder in (PRESETS, themes_dir()):
        path = os.path.join(folder, name + ".json")
        if os.path.isfile(path):
            return path
    return None


def theme_label(path, name):
    try:
        with open(path, encoding="utf-8-sig") as f:
            label = json.load(f).get("label")
    except (OSError, ValueError, AttributeError):
        label = None
    return label if isinstance(label, str) and label.strip() else name.replace("-", " ").title()


def theme_list():
    out, seen = [], set()
    for folder, builtin in ((PRESETS, True), (themes_dir(), False)):
        try:
            names = sorted(f[:-5] for f in os.listdir(folder) if f.endswith(".json") and THEME_NAME.fullmatch(f[:-5]))
        except OSError:
            names = []
        for name in names:
            if name not in seen:
                seen.add(name)
                out.append({"name": name, "label": theme_label(os.path.join(folder, name + ".json"), name), "builtin": builtin})
    return out


def default_theme():
    """The theme an overlay uses when its address names none: the one picked in the Studio, else config.json's."""
    try:
        with open(os.path.join(themes_dir(), "default.txt"), encoding="utf-8") as f:
            picked = f.read().strip()
    except OSError:
        picked = ""
    for name in (picked, (CFG.get("overlay") or {}).get("theme"), "classic"):
        if name and theme_path(name):
            return name
    return "classic"


def theme_change(body, what):
    """Save, delete or pick a theme for the Studio. Returns the answer it shows."""
    name = str(body.get("name") or "")
    if not THEME_NAME.fullmatch(name):
        return {"ok": False, "why": "A theme name is 1 to 40 lowercase letters, digits or dashes."}
    builtin = os.path.isfile(os.path.join(PRESETS, name + ".json"))
    mine = os.path.join(themes_dir(), name + ".json")
    if what == "default":
        if not theme_path(name):
            return {"ok": False, "why": "There is no theme called %s." % name}
        config_file.replace_file(os.path.join(themes_dir(), "default.txt"), name)
    elif builtin:
        return {"ok": False, "why": "%s comes with CrossChat and can't be changed. Save it under a new name." % name}
    elif what == "save":
        theme = body.get("theme")
        text = json.dumps(theme, indent=2, ensure_ascii=False)
        if not isinstance(theme, dict) or len(text.encode()) > THEME_MOST:
            return {"ok": False, "why": "A theme is a JSON object of at most %d KB." % (THEME_MOST // 1024)}
        config_file.replace_file(mine, text + "\n")
    elif os.path.isfile(mine):
        os.remove(mine)
    log.info("theme %s: %s", what, name)
    send({"type": "theme", "name": name, "default": default_theme()})
    return {"ok": True}


# ---- the featured message and test events -------------------------------------------------------------
def feature(mid):
    """Show one message big on stream (the featured-message widget), or nothing when `mid` is ''."""
    found = next((m for m in reversed(messages) if m["id"] == mid and m["kind"] in ("chat", "event")), None) if mid else None
    if mid and (not found or found.get("hidden")):
        return False                             # too old to find, or filtered: whatever is featured stays
    state["featured"] = found
    send({"type": "feature", "msg": found})
    if found and TTS["enabled"] and TTS["read"] == "featured":
        say(speech(found, force=True), found["id"])
    if found and to_discord():
        DC.featured(found)
    return True


SAMPLES = {
    "chat": [("twitch", "pixel_pirate", "this overlay looks great", "#ff7f50"), ("youtube", "Maya Chen", "hello from Lisbon!", ""),
             ("kick", "turbo_kat", "W stream", "#53fc18"), ("x", "Dev Daily", "one chat for every platform, nice", "")],
    # (platform, name, what they said, the platform's own sentence, alert, amount)
    "alert": [("twitch", "nightowl_42", "half a year already!", "nightowl_42 subscribed for 6 months!", "resub", "6"),
              ("youtube", "Sam Ortiz", "Keep it up!", "Super Chat $5.00", "superchat", "$5.00"),
              ("twitch", "raid_leader", "", "37 raiders from raid_leader have joined!", "raid", "37"),
              ("kick", "turbo_kat", "", "turbo_kat gifted 5 subs", "gift", "5 subs"),
              ("twitch", "bitbucket", "Cheer500 great stream", "bitbucket cheered 500 bits", "cheer", "500 bits"),
              ("tiktok", "sunny.daze", "", "sunny.daze sent Rose ×5", "gift", "Rose ×5")],
}


async def test_event(kind):
    """Made-up events marked test, so the overlays in your streaming app can be checked without being live."""
    global test_viewers_until
    if kind == "chat":
        for platform, name, text, color in SAMPLES["chat"]:
            publish(platform, name, text, color, mid="test-%d" % time.time_ns(), test=True)
            await asyncio.sleep(0.6)
    elif kind == "alert":
        platform, name, text, system, alert, amount = random.choice(SAMPLES["alert"])
        publish(platform, name, text, kind="event", alert=alert, amount=amount, system=system, test=True)
    elif kind == "featured":
        platform, name, text, color = random.choice(SAMPLES["chat"])
        publish(platform, name, text, color, mid="test-%d" % time.time_ns(), test=True)
        feature(messages[-1]["id"])
    elif kind == "viewers":
        test_viewers_until = time.monotonic() + TEST_VIEWERS_SECONDS
        send(viewer_event())
        await asyncio.sleep(TEST_VIEWERS_SECONDS)
        test_viewers_until = 0
        send(viewer_event())                     # back to the real numbers
    else:
        return False
    return True


# ---- replies and moderation, from the chat window or a paired device --------------------------------------
# Every reply and moderation goes through here. Twitch and Kick are done by the hub itself with their own APIs, once
# the streamer has connected them; the other platforms are handed to the "executor": the chat window on this PC that
# has the CrossChat extension, which posts as the accounts signed in to that browser.
LIMIT = {"twitch": 500, "youtube": 200, "x": 140, "kick": 500, "tiktok": 150, "facebook": 8000, "instagram": 2200, "rumble": 200}
NAMES = {"twitch": "Twitch", "youtube": "YouTube", "x": "X", "kick": "Kick", "tiktok": "TikTok", "facebook": "Facebook",
         "instagram": "Instagram", "rumble": "Rumble"}
MOD_ACTIONS = {"twitch": ("delete", "timeout", "ban", "unban"), "youtube": ("delete", "timeout", "ban"),
               "kick": ("delete", "timeout", "ban", "unban"),
               "facebook": ("delete",),                       # Live Producer's own comment menu, through the extension
               "rumble": ("delete", "timeout", "mute", "ban")}  # Rumble's chat pop-out: 5 minutes, this stream, forever
QUICK_DEFAULTS = ["Welcome in! 👋", "Thanks for the follow!", "Good question, one sec", "GG", "❤️", "Be right back, 2 minutes"]
jobs = {}                                    # job id -> future the executor's answer lands in
TW = None                                    # the Twitch API connection (set in main)
KK = None                                    # the Kick API connection (set in main)
RB = None                                    # the Rumble Live Stream API URL (set in main)
DC = None                                    # the Discord webhook chat is posted to (set in main)
DEV = None                                   # paired devices (set in main)
LOG = None                                   # this stream's chat history (set in main)
EMOTES = {}                                  # third-party emote name -> picture URL
BOTS = {"nightbot", "streamelements", "streamlabs", "moobot", "fossabot", "wizebot", "botrix", "sery_bot", "kofistreambot",
        "soundalerts", "own3d", "blerp"}            # well-known chat bots, hidden from the widgets when "bots" is on
FILTER_DEFAULTS = {"words": [], "users": [], "hide_commands": True, "bots": True, "joins": False}   # joins: show TikTok's
FILTERS = dict(FILTER_DEFAULTS)
TTS_DEFAULTS = {"enabled": False, "read": "questions", "command": "!tts", "names": True, "max_chars": 200, "skip_links": True,
                "platforms": "all", "voice": "", "rate": 1.0, "volume": 1.0}
TTS = dict(TTS_DEFAULTS)


def signed_out(platform, revoked, page):
    """The answer to Disconnect: the token is gone from this PC either way; say so when the platform didn't confirm."""
    if revoked:
        return {"ok": True}
    why = ("CrossChat deleted its %s sign-in from this PC, but %s didn't confirm it was cancelled. To be sure, remove "
           "CrossChat at %s." % (platform, platform, page))
    note(why)
    return {"ok": True, "why": why}


def rumble_event():
    if DEMO:
        return {"type": "rumble_auth", "state": "on"}
    return {"type": "rumble_auth", **(RB.state() if RB else {"state": "off"})}


def kick_event():
    if DEMO:
        return {"type": "kick_auth", "state": "on", "login": "you"}
    return {"type": "kick_auth", **(KK.state() if KK else {"state": "off"})}


# ---- Discord (posting through a webhook), the update notice, and settings the window switches ----------------------
def discord_event():
    if DEMO:
        return {"type": "discord_auth", "state": "on", "name": "stream-chat", "live": True, "featured": True, "chat": False}
    return {"type": "discord_auth", **(DC.state() if DC else {"state": "off"})}


def to_discord():
    """Chat and featured messages go to Discord only during a real stream (not a test, the demo or a stream to this PC)."""
    return bool(DC and streaming.is_set() and not TEST and not state.get("local"))


def live_notice():
    """The going-live post in Discord: where to watch, from the channels in config.json."""
    links = [("Twitch", TWITCH and "https://www.twitch.tv/" + TWITCH),
             ("YouTube", YOUTUBE and "https://www.youtube.com/%s/live" % (YOUTUBE if YOUTUBE.startswith("@") else "channel/" + YOUTUBE)),
             ("Kick", KICK and "https://kick.com/" + KICK), ("TikTok", TIKTOK and "https://www.tiktok.com/@%s/live" % TIKTOK)]
    return "\n".join(["🔴 **Live now!**"] + ["%s: %s" % (name, url) for name, url in links if url])


def save_setting(key, value):
    """A switch flipped in the window, written to config.json (the demo keeps it in memory only)."""
    if not DEMO:
        config_file.change(CONFIG_PATH, key, value)
    section, _, name = key.partition(".")
    if name:
        CFG.setdefault(section, {})[name] = value
    else:
        CFG[section] = value


update_state = {"checked": 0.0, "found": None, "wake": None}


def update_wanted():
    return (CFG.get("updates") or {}).get("check") is True and not DEMO


def update_event():
    """For the window on this PC: whether the check is on, and the newer release when there is one."""
    found = update_state["found"] if update_wanted() else None
    theirs = updates.version((found or {}).get("version"))
    newer = bool(theirs and theirs > (updates.version(VERSION) or (0,)))
    return {"type": "update", "check": update_wanted(), "version": "%d.%d.%d" % theirs if newer else "",
            "url": updates.page(theirs) if newer else ""}


async def update_watch():
    """The update notice, when switched on: GitHub is asked at most once a day. The last time is kept in your folder,
    so restarting OBS doesn't ask again."""
    update_state["wake"] = asyncio.Event()
    try:
        with open(settings_path("update-check.json"), encoding="utf-8") as f:
            saved = json.load(f)
        update_state["checked"] = float(saved.get("checked") or 0)
        update_state["found"] = saved.get("found") if isinstance(saved.get("found"), dict) else None
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    while True:
        if update_wanted() and time.time() - update_state["checked"] >= updates.DAY:
            update_state["checked"] = time.time()
            try:
                update_state["found"] = await asyncio.to_thread(updates.newest, VERSION)
            except updates.UpdateError as error:
                log.info("update check: %s", error)
            try:
                config_file.replace_file(settings_path("update-check.json"), json.dumps({"checked": update_state["checked"], "found": update_state["found"]}))
            except OSError:
                pass
            send(update_event(), only=local_clients)
        update_state["wake"].clear()
        try:
            await asyncio.wait_for(update_state["wake"].wait(), 3600)
        except asyncio.TimeoutError:
            pass


def settings_path(name):
    """Settings the app changes (tts.json, filters.json) in your folder. The demo keeps its own copies."""
    return os.path.join(HOME, name.replace(".json", "-demo.json") if DEMO else name)


def trouble(text):
    """For companion_setup, which runs in a worker thread: in the log now, and on screen once the hub is up (main)."""
    log.warning(text)
    problems.append(text)


def damaged(path, what, error):
    """Keep a settings file that can't be used as <name>.bad. Says so, in words for the streamer."""
    kept = config_file.set_aside(path)
    return "CrossChat couldn't read %s (%s), so the defaults are in use until you set them again.%s" % (
        what, error, " The damaged file is kept as %s.bad." % os.path.basename(path) if kept else "")


def settings_file(name, defaults, clean, what):
    """Those settings, laid over their defaults and checked the way the app checks them. A damaged file is kept and the
    streamer told: a filters.json that can't be read means no filtering, so hidden words would reach the stream."""
    path = settings_path(name)
    try:
        with open(path, encoding="utf-8-sig") as f:
            saved = json.load(f)
        if not isinstance(saved, dict):
            raise ValueError("not a settings file")
        return clean({**defaults, **{k: v for k, v in saved.items() if k in defaults}})
    except FileNotFoundError:
        return dict(defaults)
    except (OSError, TypeError, ValueError) as error:
        trouble(damaged(path, what, error))
        return dict(defaults)


def clean_filters(body):
    """The filter settings from the app, checked: lists of at most 200 short strings, and a flag."""
    out = dict(FILTER_DEFAULTS)
    for key in ("words", "users"):
        items = body.get(key, out[key])
        if not isinstance(items, list) or len(items) > 200 or any(not isinstance(i, str) or len(i) > 50 for i in items):
            raise ValueError("%s must be a list of up to 200 entries of up to 50 characters" % key)
        out[key] = list(dict.fromkeys(" ".join(i.split()) for i in items if i.strip()))
    out["hide_commands"] = bool(body.get("hide_commands", out["hide_commands"]))
    out["bots"] = bool(body.get("bots", out["bots"]))
    out["joins"] = body.get("joins", out["joins"]) is True
    return out


def hide_earlier():
    """New filters also hide what is already on screen: matching messages from earlier are marked and taken off."""
    for m in messages:
        if m.get("type") == "msg" and m.get("kind") == "chat" and m.get("p") != "system" and not m.get("hidden"):
            reason = hidden_reason(m.get("name", ""), m.get("text", ""), m.get("handle", ""))
            if reason:
                m["hidden"] = reason
                send({"type": "hide", "id": m["id"], "why": reason})


def clean_tts(body):
    out = dict(TTS_DEFAULTS)
    out["enabled"] = bool(body.get("enabled", False))
    out["read"] = body.get("read") if body.get("read") in ("all", "questions", "events", "command", "featured") else "questions"
    out["command"] = (str(body.get("command") or "!tts").strip() or "!tts")[:20]
    out["names"] = bool(body.get("names", True))
    out["skip_links"] = bool(body.get("skip_links", True))
    out["max_chars"] = max(20, min(int(body.get("max_chars") or 200), 500))
    platforms = body.get("platforms", "all")
    out["platforms"] = [p for p in platforms if p in NAMES] if isinstance(platforms, list) else "all"
    out["voice"] = str(body.get("voice") or "")[:120]
    out["rate"] = max(0.5, min(float(body.get("rate") or 1.0), 2.0))
    out["volume"] = max(0.0, min(float(body.get("volume") if body.get("volume") is not None else 1.0), 1.0))
    return out


# ---- reading chat aloud: the hub decides what, the CrossChat window on this PC speaks it --------------------
LINK = re.compile(r"https?://\S+|www\.\S+", re.I)


def speech(m, force=False):
    """What to say for message `m`, or '' when it shouldn't be read."""
    t = TTS
    if not force and (not t["enabled"] or m.get("hidden") or m.get("kind") not in ("chat", "event") or m.get("p") == "system"):
        return ""
    if not force and t["platforms"] != "all" and m.get("p") not in t["platforms"]:
        return ""
    if not force and m.get("alert") in ("like", "join"):
        return ""                                # too many to read out
    if set(m.get("badges") or ()) & {"broadcaster", "owner"}:
        return ""                                # never read the streamer's own lines back
    text = m.get("text") or ""
    if m.get("kind") == "event":
        text = ((m.get("system") or "") + ". " + text).strip(". ")
    if not force:
        mode = t["read"]
        if mode == "questions" and not m.get("question"):
            return ""
        if mode == "events" and m.get("kind") != "event":
            return ""
        if mode == "command":
            if not text.lower().startswith(t["command"].lower() + " "):
                return ""
            text = text[len(t["command"]) + 1:]
        if mode == "featured":
            return ""                            # read by feature() instead
    if t["skip_links"]:
        text = LINK.sub("a link", text)
    words = [w for w in text.split() if w not in EMOTES]          # emote names read badly ("KEKW")
    text = " ".join(words)[:t["max_chars"]].strip()
    if not text:
        return ""
    if t["names"] and m.get("kind") == "chat" and m.get("name"):
        text = "%s says: %s" % (m["name"], text)
    return text


def say(text, mid=""):
    if text and state.get("speaker") is not None:
        send({"type": "say", "id": mid, "text": text, "voice": TTS["voice"], "rate": TTS["rate"], "volume": TTS["volume"]},
             only=[state["speaker"]])


def speak_maybe(m):
    say(speech(m), m.get("id", ""))


# ---- third-party emotes (7TV, BetterTTV, FrankerFaceZ) ------------------------------------------------------
async def load_emotes(room_id=""):
    which = [k for k, on in (CFG.get("emotes") or {}).items() if on and k in emote_sources.SOURCES]
    if not which:
        return
    found, problems = await asyncio.to_thread(emote_sources.load, room_id, which)
    for problem in problems:
        log.info("emotes: %s", problem)
    if found:
        EMOTES.clear()
        EMOTES.update(found)
        send({"type": "emotes", "emotes": EMOTES})
        log.info("emotes: %d loaded", len(EMOTES))


async def emotes_refresh():
    """Load the emotes now (global ones, plus the channel's once Twitch says who it is) and again every hour."""
    while True:
        await load_emotes(state.get("twitch_room", ""))
        await asyncio.sleep(3600)


roles = {"executor": [], "speaker": []}       # every window that can take the role, newest last


def take_role(role, queue):
    roles[role].append(queue)
    state[role] = queue


def drop_role(role, queue):
    """A window closed: the role goes back to the newest one still open. True when the holder changed."""
    if queue in roles[role]:
        roles[role].remove(queue)
    holder = roles[role][-1] if roles[role] else None
    changed = state.get(role) is not holder
    state[role] = holder
    return changed


def executor_event():
    return {"type": "executor", "present": state["executor"] is not None}


def twitch_event():
    if DEMO:
        return {"type": "twitch_auth", "state": "on", "login": "you"}
    return {"type": "twitch_auth", **(TW.state() if TW else {"state": "off"})}


def quick_path():
    return os.path.join(HOME, "quick-demo.json" if DEMO else "quick.json")


def quick_replies():
    try:
        with open(quick_path(), encoding="utf-8-sig") as f:
            found = json.load(f)
        if not isinstance(found, list):
            raise ValueError("not a list of replies")
        return [str(r)[:100] for r in found][:30]
    except FileNotFoundError:
        return QUICK_DEFAULTS
    except (OSError, ValueError) as error:
        warn(damaged(quick_path(), "your quick replies", error))
        return QUICK_DEFAULTS


async def by_executor(job, seconds=25):
    """Hand a job to the chat window with the extension and wait for its answer (None: nobody answered)."""
    if state["executor"] is None:
        return None
    future = asyncio.get_running_loop().create_future()
    jobs[job["id"]] = future
    send({"type": "outbox", "job": job}, only=[state["executor"]])
    try:
        return await asyncio.wait_for(future, seconds)
    except asyncio.TimeoutError:
        return None
    finally:
        jobs.pop(job["id"], None)


NO_EXECUTOR = "the CrossChat window with the extension is not open on the streaming PC"
# YouTube moderation can first have to open YouTube's chat pop-out (only there does YouTube offer it): give it longer
# (the chat window's app.js waits as long, patience()).
YT_MOD_SECONDS = 75


async def run_send(job):
    text, reply_to, to = job["text"], job.get("reply") or {}, job["to"]
    answer = {}
    if DEMO:                                     # everything "works", nothing leaves this PC
        await asyncio.sleep(0.6)
        for p in to:
            publish(p, "you", text, "#e3a57b", ["broadcaster"], mid="demo-you-%d" % time.time_ns())
            await asyncio.sleep(0.15)
        send({"type": "sent", "job_id": job["id"], "answer": {p: {"ok": True} for p in to}})
        return
    if "twitch" in to and not (TW and TW.on()):
        answer["twitch"] = {"ok": False, "why": "Connect Twitch in Settings to reply on Twitch"}
        to = [p for p in to if p != "twitch"]
    if "kick" in to:
        answer["kick"] = await kick_send(job, text, reply_to)
        to = [p for p in to if p != "kick"]
    if "twitch" in to and TW and TW.on() and TWITCH:
        if job["dry"]:
            answer["twitch"] = {"ok": False, "why": "test mode, nothing is posted"}
        else:
            parent = reply_to.get("id", "") if reply_to.get("p") == "twitch" else ""
            said = text
            if parent and text.lower().startswith("@" + str(reply_to.get("name", "")).lower() + " "):
                said = text[len(reply_to["name"]) + 2:]       # a threaded reply gets its @name from Twitch
            try:
                await asyncio.to_thread(TW.send, TWITCH, said, re.sub(r"[^\w-]", "", parent))
                answer["twitch"] = {"ok": True}
            except (TwitchError, requests.RequestException) as error:
                answer["twitch"] = {"ok": False, "why": str(error) or "Twitch did not answer"}
        to = [p for p in to if p != "twitch"]
    if to:
        got = await by_executor({**job, "to": to})
        for p in to:
            answer[p] = (got or {}).get(p) or {"ok": False, "why": NO_EXECUTOR if got is None else "no answer"}
    send({"type": "sent", "job_id": job["id"], "answer": answer})


async def kick_send(job, text, reply_to):
    if not (KK and KK.on()):
        return {"ok": False, "why": "Connect Kick in Settings to reply on Kick"}
    if job["dry"]:
        return {"ok": False, "why": "test mode, nothing is posted"}
    parent = reply_to.get("id", "") if reply_to.get("p") == "kick" else ""
    try:
        await asyncio.to_thread(KK.send, KICK, text, re.sub(r"[^\w-]", "", parent))
        return {"ok": True}
    except (KickError, requests.RequestException, ValueError) as error:
        return {"ok": False, "why": str(error) or "Kick did not answer"}


async def run_mod(job):
    p, action = job["p"], job["action"]
    if DEMO:
        await asyncio.sleep(0.5)
        target = next((m for m in messages if m.get("mid") == job.get("message_id") or m.get("uid") == job.get("user_id")), None)
        if action == "delete" and target:
            send({"type": "delete", "id": target["id"]})
        elif action in ("timeout", "ban") and target:
            send({"type": "purge", "p": p, "name": target["name"].lower()})
        send({"type": "sent", "job_id": job["id"], "answer": {"ok": True}})
        return
    if p == "twitch":
        if not (TW and TW.on()):
            answer = {"ok": False, "why": "Connect Twitch in Settings to moderate Twitch chat."}
        else:
            try:
                await asyncio.to_thread(TW.moderate, TWITCH, action, job.get("user_id", ""), job.get("message_id", ""),
                                        job.get("seconds", 0), job.get("reason", ""))
                answer = {"ok": True}
            except (TwitchError, requests.RequestException) as error:
                answer = {"ok": False, "why": str(error) or "Twitch did not answer"}
    elif p == "kick":
        if not (KK and KK.on()):
            answer = {"ok": False, "why": "Connect Kick in Settings to moderate Kick chat."}
        else:
            try:
                await asyncio.to_thread(KK.moderate, KICK, action, job.get("user_id", ""), job.get("message_id", ""),
                                        job.get("seconds", 0), job.get("reason", ""))
                answer = {"ok": True}
            except (KickError, requests.RequestException, ValueError) as error:
                answer = {"ok": False, "why": str(error) or "Kick did not answer"}
    else:
        answer = await by_executor(job, YT_MOD_SECONDS if p == "youtube" else 25) or {"ok": False, "why": NO_EXECUTOR}
    log.info("moderation %s on %s: %s", action, p, "done" if answer.get("ok") else answer.get("why"))
    send({"type": "sent", "job_id": job["id"], "answer": answer})


def new_send(body):
    """Check a reply and start it. Returns the answer the asking page gets at once (its outcome comes as `sent`)."""
    text = " ".join(str(body.get("text") or "").split())          # one line: nothing typed can become a chat command
    to = [p for p in dict.fromkeys(body.get("to") or []) if p in LIMIT]
    if not text or not to:
        return {"ok": False, "why": "nothing to send" if not text else "no platform to send to"}
    too_long = [NAMES[p] for p in to if len(text) > LIMIT[p]]
    if too_long:
        return {"ok": False, "why": "too long for " + ", ".join(too_long)}
    reply_to = body.get("reply") if isinstance(body.get("reply"), dict) else None
    job = {"id": secrets.token_hex(8), "kind": "send", "to": to, "text": text, "reply": reply_to, "dry": bool(body.get("dry"))}
    spawn(run_send(job))
    return {"ok": True, "job_id": job["id"]}


def new_mod(body):
    p, action = str(body.get("p") or ""), str(body.get("action") or "")
    if action not in MOD_ACTIONS.get(p, ()):
        return {"ok": False, "why": "%s can't %s from CrossChat" % (NAMES.get(p, p or "That platform"), action or "do that")}
    job = {"id": secrets.token_hex(8), "kind": "mod", "p": p, "action": action, "name": str(body.get("name") or "")[:60],
           "message_id": re.sub(r"[^\w.:=-]", "", str(body.get("message_id") or ""))[:120],
           "user_id": re.sub(r"[^\w.:=-]", "", str(body.get("user_id") or ""))[:120],
           "seconds": max(0, min(int(body.get("seconds") or 0), 1209600)) if str(body.get("seconds") or "0").isdigit() else 600,
           "reason": " ".join(str(body.get("reason") or "").split())[:200], "video": state["youtube_video"]}
    if p == "rumble":
        # Rumble's API gives chat lines no id, so the extension finds the line in Rumble's chat by name and words: the
        # hub's own copy of the message says which, whatever the page sent.
        said = next((m for m in reversed(messages) if m.get("p") == "rumble" and m.get("mid") == job["message_id"]), None)
        if not said:
            return {"ok": False, "why": "That Rumble message is no longer in the chat"}
        job["name"], job["text"] = said["name"][:60], said["text"][:500]
        if action == "timeout":
            job["seconds"] = 300                 # Rumble's only timed mute
    spawn(run_mod(job))
    return {"ok": True, "job_id": job["id"]}


def set_star(mid, on):
    if on and mid not in starred and any(m["id"] == mid for m in messages):
        starred.append(mid)
    elif not on and mid in starred:
        starred.remove(mid)
    send({"type": "starred", "ids": list(starred)})


async def twitch_connect():
    """Twitch's device sign-in: show the code, then wait for the streamer to enter it at twitch.tv/activate."""
    try:
        pending = await asyncio.to_thread(TW.start)
    except (TwitchError, requests.RequestException) as error:
        TW.why = str(error)
        send(twitch_event())
        return
    send(twitch_event())
    while TW.pending is pending:
        await asyncio.sleep(pending["interval"])
        try:
            if await asyncio.to_thread(TW.poll):
                log.info("Twitch connected as %s", TW.user.get("login"))
                break
        except (TwitchError, requests.RequestException) as error:
            TW.why = str(error)
            break
    send(twitch_event())


# ---- the companion: paired devices on the home network --------------------------------------------------
remote_server = None
remote_address = ""     # where the companion listens
remote_why = ""         # why it doesn't, for the Pair button
PUBLIC_NETWORK = ("The companion stays off: Windows has this network down as Public, where other people could listen in. "
                  "On your home network, set it to Private (Settings > Network & internet > your network > Private network).")


def lan_ip():
    """This PC's address on the home network (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def remote_port():
    return int((CFG.get("remote") or {}).get("port") or 4467)


def lan_url():
    host = remote_bind() if remote_bind() not in ("auto", "0.0.0.0") else lan_ip()
    return "http://%s:%d/" % (host, remote_port()) if (CFG.get("remote") or {}).get("enabled", True) else None


def network_category(ip):
    """How Windows rates the network that address is on: "Private", "DomainAuthenticated", "Public", or '' if unknown.
    A Mac or Linux has no such rating, so there it's always unknown (and the companion only listens where "bind" says)."""
    if MAC or LINUX:
        return ""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                              "(Get-NetIPAddress -IPAddress '%s' -ErrorAction Stop | Get-NetConnectionProfile -ErrorAction Stop).NetworkCategory"
                              % re.sub(r"[^\d.]", "", ip)], capture_output=True, text=True, timeout=15, creationflags=NO_WINDOW)
        return out.stdout.strip().splitlines()[0] if out.returncode == 0 and out.stdout.strip() else ""
    except (OSError, subprocess.SubprocessError, IndexError):
        return ""


async def network_refusal(address):
    """Why the companion may not listen on this network, or '' when it's a home (Private) network. When Windows can't
    say, the answer is no: better a companion that won't start than one listening on a café's Wi-Fi."""
    if address == "127.0.0.1":
        return "This PC is not on a network."
    category = await asyncio.to_thread(network_category, address)
    if category in ("Private", "DomainAuthenticated"):
        return ""
    if category == "Public":
        return PUBLIC_NETWORK
    if MAC:
        return ("The companion stays off: macOS doesn't tell apps whether a network is a private one, so CrossChat won't "
                "guess. On your home network, set \"remote\": {\"bind\": \"%s\"} in config.json to use it there." % address)
    if LINUX:
        return ("The companion stays off: Linux doesn't tell apps whether a network is a private one, so CrossChat won't "
                "guess. On your home network, set \"remote\": {\"bind\": \"%s\"} in config.json to use it there." % address)
    return ("The companion stays off: CrossChat couldn't ask Windows whether this network is a private one. To use it "
            "anyway, set \"remote\": {\"bind\": \"%s\"} in config.json." % address)


async def remote_on():
    """The companion, on the home network and (when switched on) on Tailscale."""
    await lan_on()
    await tailscale_on()


async def lan_on():
    """Listen on the home network once there is a paired device or a pairing in progress (not before, so nothing is
    exposed and Windows doesn't ask about the firewall until the streamer pairs something).

    It listens only on this PC's address on the home network (not on every network adapter, such as a VPN), and
    not at all when Windows has that network down as Public (a café or hotel network, where others could listen in).
    For away from home there is "remote": {"tailscale": true} (see tailscale_on); "remote": {"bind": "0.0.0.0"} in
    config.json listens everywhere instead.
    """
    global remote_server, remote_address, remote_why
    if remote_server or not (CFG.get("remote") or {}).get("enabled", True) or not (DEV.devices or DEV.pairing_open()):
        return
    bind = remote_bind()
    address = lan_ip() if bind == "auto" else bind
    if bind == "auto":
        why = await network_refusal(address)
        if why:
            if remote_why != why and address != "127.0.0.1":
                warn(why)
            remote_why = why
            return
    try:
        remote_server = await asyncio.start_server(lambda r, w: serve(r, w, remote=True), address, remote_port())
        remote_address, remote_why = address, ""
        log.info("companion on %s (listening on %s)", lan_url(), address)
    except OSError as error:
        remote_why = "CrossChat could not open port %d for the companion (%s)." % (remote_port(), error.strerror)
        warn(remote_why + " Change \"remote\": {\"port\"} in config.json.")


def remote_bind():
    return str((CFG.get("remote") or {}).get("bind") or "auto")


def lan_off():
    global remote_server
    if remote_server:
        remote_server.close()
        remote_server = None


async def remote_off():
    lan_off()
    await tailscale_off()


# Tailscale: the streamer's own devices in one private, encrypted network, so the phone reaches the companion from
# anywhere. Only on the PC's own Tailscale address (see tailscale.py), only when switched on, and pairing is still needed.
tailscale_server = None
tailscale_address = ""  # where it listens
tailscale_seen = ""     # this PC's Tailscale address when last looked
tailscale_why = ""      # why it doesn't listen there, for Settings
TAILSCALE_MISSING = ("Tailscale isn't running on this PC. Install it from tailscale.com and sign in, here and on your phone, "
                     "then pair the phone again.")


def tailscale_wanted():
    remote = CFG.get("remote") or {}
    return remote.get("tailscale") is True and remote.get("enabled", True) is not False and remote_bind() != "0.0.0.0" and not DEMO


def tailscale_url():
    return "http://%s:%d/" % (tailscale_address, remote_port()) if tailscale_server else None


def companion_event():
    """For Settings on this PC: the Tailscale switch, this PC's Tailscale address, and why the companion isn't there."""
    return {"type": "companion", "tailscale": (CFG.get("remote") or {}).get("tailscale") is True, "address": tailscale_seen,
            "listening": bool(tailscale_server), "why": tailscale_why if tailscale_wanted() else ""}


async def tailscale_on():
    """Also listen on this PC's Tailscale address, when switched on and something is paired or pairing. When Tailscale
    isn't running, Settings says so."""
    global tailscale_server, tailscale_address, tailscale_seen, tailscale_why
    if tailscale_server or not tailscale_wanted():
        return
    tailscale_seen = await asyncio.to_thread(tailscale.address)
    tailscale_why = "" if tailscale_seen else TAILSCALE_MISSING
    if tailscale_seen and (DEV.devices or DEV.pairing_open()) and not (remote_server and remote_address == tailscale_seen):
        try:
            tailscale_server = await asyncio.start_server(lambda r, w: serve(r, w, remote=True), tailscale_seen, remote_port())
            tailscale_address = tailscale_seen
            log.info("companion on Tailscale at %s", tailscale_url())
        except OSError as error:
            tailscale_why = "CrossChat could not open port %d on the Tailscale address (%s)." % (remote_port(), error.strerror)
    send(companion_event(), only=local_clients)


async def tailscale_off():
    global tailscale_server, tailscale_address
    if tailscale_server:
        tailscale_server.close()
        tailscale_server, tailscale_address = None, ""
        log.info("the companion stopped listening on Tailscale")
        send(companion_event(), only=local_clients)


async def remote_watch():
    """The companion closes when nothing is paired any more, and when the network changes: a laptop taken from home to
    a café, or a network switched to Public. It opens again only on a Private network. On Tailscale it closes when
    Tailscale stops (or the switch goes off), and opens when Tailscale comes back."""
    rounds = 0
    while True:
        await asyncio.sleep(30)
        rounds += 1
        await companion_round(rounds)


async def companion_round(rounds):
    paired = bool(DEV.devices or DEV.pairing_open())
    if (remote_server or tailscale_server) and not paired:
        log.info("nothing is paired any more; the companion closes")
        await remote_off()
        return
    if remote_server and remote_bind() == "auto" and (lan_ip() != remote_address or (rounds % 4 == 0 and await network_refusal(remote_address))):
        log.info("this PC is on another network now; the companion starts over")
        lan_off()
        await lan_on()
    if tailscale_server and (not tailscale_wanted() or await asyncio.to_thread(tailscale.address) != tailscale_address):
        await tailscale_off()                    # Tailscale stopped, or has another address now
    if not tailscale_server and tailscale_wanted() and paired:
        await tailscale_on()


def devices_event():
    return {"type": "devices", "devices": DEV.listing() if DEV else []}


PAIR_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light"><title>Pair with CrossChat</title><link rel="icon" href="/web/crosschat.ico">
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;font-family:"Segoe UI Variable Text","Segoe UI",system-ui,sans-serif;
background:#0d141c;color:#f0e8dc}@media(prefers-color-scheme:light){body{background:#f6f1e9;color:#1d2733}}main{width:min(360px,90vw);text-align:center}
h1{font-size:24px;margin:0 0 8px}p{opacity:.8;line-height:1.5}input{width:100%;box-sizing:border-box;font:600 28px "Cascadia Mono",Consolas,monospace;
letter-spacing:.3em;text-align:center;padding:12px;border-radius:12px;border:1px solid #b87045;background:transparent;color:inherit;margin:12px 0}
button{width:100%;padding:14px;border:0;border-radius:12px;background:#b87045;color:#fff;font:inherit;font-weight:700;font-size:16px;cursor:pointer}#why{color:#e8a34a;min-height:1.5em}
</style></head><body><main><h1>Pair with CrossChat</h1><p>On the streaming PC, open the CrossChat window, Settings, <b>Pair a device</b>,
and type the 6-digit code here.</p><form id="f"><input id="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" aria-label="Pairing code"
required pattern="[0-9]{6}"><button>Pair this device</button></form><p id="why" role="alert"></p></main><script>
document.getElementById('f').onsubmit=async(e)=>{e.preventDefault();const r=await fetch('/pair',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({code:document.getElementById('code').value})}).then(r=>r.json()).catch(()=>({ok:false,why:'CrossChat did not answer.'}));
if(r.ok)location.replace('/');else document.getElementById('why').textContent=r.why||'That code did not work.';};</script></body></html>""".encode()

COOKIE = "cc_device"


def device_cookie(token):
    return "Set-Cookie: %s=%s; Path=/; Max-Age=31536000; HttpOnly; SameSite=Strict\r\n" % (COOKIE, token)


def cookie_token(headers):
    for part in headers.get("cookie", "").split(";"):
        key, _, value = part.strip().partition("=")
        if key == COOKIE:
            return value
    return ""


def pair_device(code, headers):
    token = DEV.pair(code, device_name(headers.get("user-agent", "")))
    if token:
        log.info("paired a device")
        send(devices_event(), only=local_clients)
    return token


REMOTE_GET = ("/", "/events", "/whoami", "/version", "/viewer")
REMOTE_POST = ("/send", "/mod", "/feature", "/star", "/quick", "/test", "/tts/say", "/tts/skip")


# ---- the demo stream (--demo): made-up people and lines, nothing real ------------------------------------
DEMO_PEOPLE = {
    "twitch": [("pixel_pirate", "#ff7f50", []), ("nightowl_42", "#1e90ff", ["moderator"]), ("kiwi_codes", "#9acd32", ["subscriber"]),
               ("AriaPlays", "#ff69b4", ["vip"]), ("bitbucket", "#daa520", []), ("quietstorm", "#00ced1", ["subscriber"])],
    "youtube": [("Maya Chen", "", ["member"]), ("Sam Ortiz", "", []), ("Rafael Gomes", "", []), ("Priya N", "", ["member"])],
    "kick": [("turbo_kat", "#53fc18", []), ("glitchfox", "#f5a623", [])],
    "x": [("Dev Daily", "", []), ("Lena Park", "", []), ("byte bandit", "", [])],
    "tiktok": [("sunny.daze", "", []), ("lofi.leo", "", []), ("mira_makes", "", [])],
    "facebook": [("Ines Moreau", "", []), ("Tom Okafor", "", []), ("June Alvarez", "", [])],
    "instagram": [("ines.draws", "", []), ("kai.on.film", "", []), ("noor.studio", "", [])],
    "rumble": [("GrizzlyGrant", "", ["premium"]), ("mapleleaf_mo", "", []), ("DeepDiveDan", "", [])],
}
DEMO_LINES = ["hello from Lisbon 👋", "what are we building today?", "this overlay looks so clean", "W stream", "first time catching this live!",
              "how long have you been streaming today?", "can you explain that last part again?", "lol that bug 😂", "is this open source?",
              "gg that was close", "which font is that?", "the audio sounds great", "drop the settings pls 🙏", "chat is moving fast today",
              "love the theme", "does it work with Kick too?", "back from lunch, what did I miss?", "LET'S GO", "huge fan of the new layout",
              "how do replies reach every platform?"]
DEMO_PREFIX = {"twitch": "tw", "youtube": "yt", "kick": "kk", "x": "x", "tiktok": "tt", "facebook": "fb", "instagram": "ig", "rumble": "rm"}
DEMO_WEIGHTS = {"twitch": 4, "youtube": 3, "kick": 1, "x": 2, "tiktok": 3, "facebook": 2, "instagram": 2, "rumble": 1}    # who talks most


async def demo_stream():
    """A believable live stream on every platform, so CrossChat can be tried (and filmed) without going live."""
    rng = random.Random(7)
    counts = {"twitch": 128, "youtube": 342, "kick": 41, "x": 87, "tiktok": 263, "facebook": 58, "instagram": 94, "rumble": 36}
    status.update({p: "on" for p in counts})
    now = int(time.time() * 1000)
    health.update({p: {"since": now - (i + 1) * 754000, "last": now, "reconnects": 1 if p == "kick" else 0} for i, p in enumerate(counts)})
    viewers.update(counts)
    send(status_event())
    send(viewer_event())
    n = 0
    while True:
        await asyncio.sleep(rng.uniform(1.4, 3.4))
        n += 1
        if n % 9 == 0:
            platform, name, text, system, alert, amount = rng.choice(SAMPLES["alert"])
            publish(platform, name, text, kind="event", alert=alert, amount=amount, system=system, mid="demo-%d" % time.time_ns())
        else:
            platform = rng.choices(list(DEMO_PEOPLE), weights=[DEMO_WEIGHTS[p] for p in DEMO_PEOPLE])[0]
            name, color, badges = rng.choice(DEMO_PEOPLE[platform])
            raw, handle = "demo%d" % time.time_ns(), re.sub(r"\W", "", name.lower())
            publish(platform, name, rng.choice(DEMO_LINES), color, badges, mid=DEMO_PREFIX[platform] + "-" + raw, raw=raw,
                    uid="demo-" + handle, handle=handle if platform == "x" else "")
        if n % 4 == 0:
            for p in counts:
                counts[p] = max(1, counts[p] + rng.randint(-3, 7))
            viewers.update(counts)
            send(viewer_event())


# ---- the pages and their live feed ------------------------------------------------------------------
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".svg": "image/svg+xml", ".ico": "image/x-icon", ".png": "image/png", ".webmanifest": "application/manifest+json",
         ".json": "application/json"}
OPEN = "Access-Control-Allow-Origin: *\r\n"    # who may read it is decided in refused(): this only lets them
# The CrossChat window, the Studio and the pairing page can't be put in another site's frame (where a hidden frame
# could take the streamer's clicks).
NO_FRAMES = "X-Frame-Options: DENY\r\nContent-Security-Policy: frame-ancestors 'none'; object-src 'none'; base-uri 'none'\r\n"
# The widgets OBS shows: they load only the hub's own files, emote pictures and Google Fonts. A theme's custom CSS
# can't fetch anything from elsewhere (which would tell that server the streamer's address each time OBS loads it).
OVERLAY_CSP = ("Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
               "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https://cdn.7tv.app https://cdn.betterttv.net "
               "https://cdn.frankerfacez.com https://static-cdn.jtvnw.net; media-src 'self'; connect-src 'self'; object-src 'none'; "
               "base-uri 'none'; form-action 'none'\r\n")
# Your own overlay pages (custom_overlays) get an address of their own, http://localhost:<port>/custom/, which the
# browser keeps apart from the CrossChat window's http://127.0.0.1:<port>/. They read the public chat feed and their
# own files, but can't reply, moderate, read history, change settings or script the CrossChat window, so an overlay
# downloaded from somewhere can't act as you.
READ_ONLY = ("/events", "/settings", "/version", "/themes")      # what your overlay pages may read
OVERLAY_ZONE = ("/custom/", "/web/", "/overlay/", "/themes/")    # ... and load, at their own address
BODY_LIMIT = 256 * 1024


def page(*path):
    with open(os.path.join(*path), "rb") as f:
        return f.read()


def html_text(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


CUSTOM_TYPES = {**TYPES, ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif", ".webm": "video/webm",
                ".mp4": "video/mp4", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8", ".mp3": "audio/mpeg", ".ogg": "audio/ogg"}


def custom_file(path):
    """A file of your own overlay folder ("custom_overlays" in config.json) for /custom/<path>, or None.

    OBS 33 doesn't let a page opened as a local file reach the hub, so your own overlays that read /events are loaded
    from here instead. Only files inside that folder, of the kinds listed above, are served.
    """
    root = CFG.get("custom_overlays") or ""
    if not root or not re.fullmatch(r"[\w .-]+(/[\w .-]+)*", path) or ".." in path.split("/"):
        return None
    root = os.path.realpath(os.path.expandvars(root))
    full = os.path.realpath(os.path.join(root, *path.split("/")))
    if os.path.commonpath([root, full]) != root or not os.path.isfile(full) or os.path.splitext(full)[1].lower() not in CUSTOM_TYPES:
        return None
    return full


async def reply(writer, code, kind, body, extra=""):
    writer.write(("HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nCache-Control: no-store\r\n%sConnection: close\r\n\r\n"
                  % (code, kind, len(body), extra)).encode() + body)
    await writer.drain()


def overlay_address(headers):
    """Addressed to your overlay pages' own address (localhost) rather than the CrossChat window's (127.0.0.1)."""
    return headers.get("host", "") == "localhost:%d" % PORT


def from_overlay_page(headers):
    """Sent by one of your overlay pages to the CrossChat address. No website can make the browser say this."""
    return headers.get("origin", "") == "http://localhost:%d" % PORT


def from_elsewhere(headers, home=None):
    """Sent by a page from another website (or another site's frame), not by the pages at `home`, OBS or a program."""
    return (headers.get("sec-fetch-site") in ("cross-site", "same-site")
            or headers.get("origin", "") not in ("", home or "http://127.0.0.1:%d" % PORT))


def obs_retry(method, headers, path):
    """The streamer clicking OBS's "Click here to retry" in the CrossChat dock. OBS loads a dock once, as it starts; when
    the hub wasn't answering yet, the dock shows OBS's own error page, which has an origin of its own (a data: page), so
    the click comes as another site's. Only a click (Sec-Fetch-User) that opens the chat window itself, as a whole page,
    inside OBS's own browser (its User-Agent, which no website can set, says OBS/) counts."""
    return (method == "GET" and path == "/" and headers.get("sec-fetch-mode") == "navigate" and headers.get("sec-fetch-dest") == "document"
            and headers.get("sec-fetch-user") == "?1" and " OBS/" in headers.get("user-agent", ""))


def refused(method, headers, path):
    """Why a request is turned away, or '' when it is fine.

    Only this PC's own addresses are answered (a web page can't reach the hub under another name). Anything that does
    something (open a window, start or end a livestream) is refused when another website asks for it; the OBS
    script, the Start-menu shortcuts, the extension and the hub's own pages are fine. Changes (POST) come only from
    the hub's own pages, as JSON, which a page elsewhere can't send without the browser asking first.
    """
    if headers.get("host", "") not in ("127.0.0.1:%d" % PORT, "localhost:%d" % PORT):
        return "not this address"
    # /kick/callback is Kick's own redirect back to this PC: a top-level visit from id.kick.com. It is only acted on
    # with the one-time state this hub made when the streamer pressed Connect Kick.
    if path == "/kick/callback" and method == "GET":
        return ""
    if overlay_address(headers):                 # your overlay pages' address: their files and the public chat, nothing more
        if method != "GET" or from_elsewhere(headers, "http://localhost:%d" % PORT):
            return "not from another website"
        if not (path in READ_ONLY or path == "/favicon.ico" or path.startswith(OVERLAY_ZONE)):
            return "not for overlay pages"
        return ""
    origin = headers.get("origin", "")
    outsider = from_elsewhere(headers)
    # Pages and files may be loaded from anywhere (a browser doesn't let another site read them); the live data only by
    # your overlay pages.
    readable = method == "GET" and (path.startswith(("/overlay/", "/web/", "/custom/")) or (
        from_overlay_page(headers) and (path in READ_ONLY or path.startswith("/themes/")))) or obs_retry(method, headers, path)
    if outsider and not readable and not (method == "GET" and origin.startswith("chrome-extension://")):
        return "not from another website"
    if method == "POST" and (outsider or headers.get("content-type", "").split(";")[0].strip() != "application/json"):
        return "not from another website"
    return ""


def remote_refused(method, headers, path, device):
    """For the companion port: why a request is turned away, or ''. Everything needs a paired device's cookie except
    pairing itself; changes must come from the companion page itself, as JSON. The address must be a plain IP: a
    website that points its own name at this PC (DNS rebinding) is turned away before it can even try a code."""
    if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}(:\d{1,5})?", headers.get("host", "")):
        return "not this address"
    if path == "/pair":
        pass
    elif not device:
        return "pair this device first"
    elif not (path in (REMOTE_GET if method == "GET" else REMOTE_POST) or (method == "GET" and path.startswith("/web/"))):
        return "not available on a paired device"
    if method == "POST" and (headers.get("origin", "") != "http://" + headers.get("host", "-")
                             or headers.get("content-type", "").split(";")[0].strip() != "application/json"):
        return "not from another website"
    return ""


HEAD_LIMIT, HEAD_LINES, HEAD_SECONDS = 16 * 1024, 100, 10   # a request's first line and headers
REMOTE_CONNECTIONS = 64                      # at once on the companion port: more are turned away
remote_open = 0
VIEWER_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="viewer")   # viewer cards and chat history, one at a time


def log_export(name, kind):
    """One stream's chat history as a file (None: no such stream). Reads the whole stream, so it runs in VIEWER_POOL."""
    if kind == "csv":
        return LOG.csv(name)
    if kind == "html":
        return LOG.html(name)
    rows = LOG.messages(name)
    return json.dumps(rows, ensure_ascii=False).encode() if rows is not None else None


async def read_head(reader):
    """The request line and headers, or None when they are too big, too many or too slow (so nobody on the network can
    tie the hub up by sending headers forever)."""
    lines, size = [], 0
    while True:
        line = await reader.readline()
        size += len(line)
        if size > HEAD_LIMIT or len(lines) > HEAD_LINES:
            return None
        if line in (b"\r\n", b"\n", b""):
            break
        lines.append(line.decode("latin1"))
    if not lines:
        return None
    headers = {}
    for line in lines[1:]:
        key, _, value = line.partition(":")
        headers[key.strip().lower()] = value.strip()
    return lines[0].split(), headers


async def serve(reader, writer, remote=False):
    global remote_open
    if remote:
        remote_open += 1
    try:
        if remote and remote_open > REMOTE_CONNECTIONS:
            return
        try:
            head = await asyncio.wait_for(read_head(reader), HEAD_SECONDS)
        except ValueError:                         # one line longer than the reader takes
            head = None
        if not head:
            return
        request, headers = head
        if len(request) < 2 or request[0] not in ("GET", "POST"):
            return
        method = request[0]
        url = urllib.parse.urlsplit(request[1])
        query = urllib.parse.parse_qs(url.query)
        if ready and url.path != "/version":       # (still reading the sign-ins: nothing but "who are you" works yet)
            await ready.wait()
        device = DEV.check(cookie_token(headers)) if remote and DEV else None
        why = remote_refused(method, headers, url.path, device) if remote else refused(method, headers, url.path)
        if remote and method == "GET" and why != "not this address" and (url.path == "/pair" or (url.path == "/" and not device)):
            token = pair_device((query.get("code") or [""])[0], headers) if query.get("code") else None
            if token:                              # the link from the QR code: paired, on to the companion
                await reply(writer, "303 See Other", "text/plain", b"", "Location: /\r\n" + device_cookie(token))
            else:
                await reply(writer, "200 OK", TYPES[".html"], PAIR_PAGE, NO_FRAMES)
        elif why:
            await reply(writer, "401 Unauthorized" if why.startswith("pair") else "403 Forbidden", "text/plain", why.encode())
        elif method == "POST":
            await serve_post(reader, writer, headers, url.path, remote)
        elif url.path == "/whoami":
            body = {"remote": remote, "device": device["name"] if device else None, "version": VERSION, "lan_url": lan_url(), "app": state.get("app", "")}
            await reply(writer, "200 OK", TYPES[".json"], json.dumps(body).encode())
        elif url.path == "/":
            await reply(writer, "200 OK", TYPES[".html"], page(WEB, "window.html"), NO_FRAMES)
        elif url.path == "/favicon.ico":           # browsers ask for it by themselves (OBS's overlays too)
            await reply(writer, "200 OK", TYPES[".ico"], page(WEB, "crosschat.ico"))
        elif url.path == "/studio":                # the Theme Studio
            await reply(writer, "200 OK", TYPES[".html"], page(WEB, "studio.html"), NO_FRAMES)
        elif url.path.startswith("/overlay/") and url.path[9:] in WIDGETS:     # what viewers see: OBS browser sources
            await reply(writer, "200 OK", TYPES[".html"], page(WEB, "overlay.html"), OVERLAY_CSP)
        elif re.fullmatch(r"/web/(vendor/)?[\w-]+\.(js|css|svg|ico|png|webmanifest)", url.path):
            await reply(writer, "200 OK", TYPES[os.path.splitext(url.path)[1]], page(WEB, url.path[5:]), OPEN)
        elif url.path == "/logs" and LOG:               # chat history (this PC only)
            listing = await asyncio.get_running_loop().run_in_executor(VIEWER_POOL, LOG.listing)     # (every line of every file: not on the loop)
            await reply(writer, "200 OK", TYPES[".json"], json.dumps({"logs": listing}).encode())
        elif re.fullmatch(r"/logs/[\w-]+\.(json|csv|html)", url.path) and LOG:
            name, kind = url.path[6:].rsplit(".", 1)
            body = await asyncio.get_running_loop().run_in_executor(VIEWER_POOL, log_export, name, kind)
            if body is None:
                await reply(writer, "404 Not Found", "text/plain", b"no such chat history")
            else:
                types = {"json": TYPES[".json"], "csv": "text/csv; charset=utf-8", "html": TYPES[".html"]}
                extra = "" if kind == "json" else 'Content-Disposition: attachment; filename="crosschat-%s.%s"\r\n' % (name, kind)
                await reply(writer, "200 OK", types[kind], body, extra)
        elif url.path == "/config/editable" and not remote:     # Settings → Channels & options (no tokens or secrets)
            await reply(writer, "200 OK", TYPES[".json"], json.dumps(settings_ui.editable(CFG)).encode())
        elif url.path == "/viewer":                    # a viewer card: this PC and paired devices
            first = lambda k: (query.get(k) or [""])[0]
            history = LOG and not DEMO                  # the demo never shows your real chat history
            args = (first("p"), first("name"), first("uid"), first("q"), list(messages), LOG.folder if history else None,
                    LOG.name if history and LOG.file else None, NAMES)
            try:                                        # one at a time: each reads up to a fixed amount of history
                card = await asyncio.get_running_loop().run_in_executor(VIEWER_POOL, viewer_cards.lookup, *args)
                await reply(writer, "200 OK", TYPES[".json"], json.dumps(card, ensure_ascii=False).encode())
            except viewer_cards.ViewerError as error:
                await reply(writer, "400 Bad Request", TYPES[".json"], json.dumps({"ok": False, "why": str(error)}).encode())
        elif url.path == "/kick/callback":            # Kick sends the browser back here after the streamer signs in
            code, got_state = (query.get("code") or [""])[0], (query.get("state") or [""])[0]
            try:
                if not code:
                    raise KickError((query.get("error_description") or query.get("error") or ["Kick did not sign in."])[0])
                await asyncio.to_thread(KK.finish, code, got_state)
                log.info("Kick connected as %s", KK.user.get("login"))
                text = "Kick is connected to CrossChat as %s. You can close this tab." % KK.user.get("login", "")
            except (KickError, requests.RequestException, KeyError, ValueError) as error:
                KK.why = str(error)
                text = "Kick was not connected: %s" % error
            send(kick_event())
            page_ = ("<!doctype html><meta charset=utf-8><title>CrossChat</title><body style=\"font:16px 'Segoe UI',sans-serif;"
                     "background:#0d141c;color:#f0e8dc;display:grid;place-items:center;height:90vh\"><p>%s</p>" % html_text(text)).encode()
            await reply(writer, "200 OK", TYPES[".html"], page_, NO_FRAMES)
        elif url.path.startswith("/custom/") and not overlay_address(headers):   # an old 127.0.0.1 address: to their own
            await reply(writer, "302 Found", "text/plain", b"", "Location: http://localhost:%d%s\r\n" % (PORT, request[1]))
        elif url.path.startswith("/custom/"):          # your own overlay pages (custom_overlays in config.json)
            found = custom_file(urllib.parse.unquote(url.path[8:]))
            if found:                                  # no CORS: other sites can't read them
                await reply(writer, "200 OK", CUSTOM_TYPES[os.path.splitext(found)[1].lower()], page(found))
            else:
                await reply(writer, "404 Not Found", "text/plain", b"not found")
        elif url.path == "/themes":
            await reply(writer, "200 OK", TYPES[".json"], json.dumps({"default": default_theme(), "themes": theme_list()}).encode(), OPEN)
        elif url.path.startswith("/themes/"):
            path = theme_path(url.path[8:])
            if path:
                await reply(writer, "200 OK", TYPES[".json"], page(path), OPEN)
            else:
                await reply(writer, "404 Not Found", "text/plain", b"no such theme")
        elif url.path == "/feature":               # the chat window's feature button, or the OBS hotkey that clears it
            ok = feature("" if query.get("clear") else (query.get("id") or [""])[0])
            await reply(writer, "200 OK", TYPES[".json"], json.dumps({"ok": ok}).encode())
        elif url.path == "/settings":              # what the on-stream chat overlay should show
            body = {"overlay": CFG.get("overlay") or {}, "theme": default_theme()}
            await reply(writer, "200 OK", "application/json", json.dumps(body).encode(), OPEN)
        elif url.path == "/version":
            await reply(writer, "200 OK", "application/json", json.dumps({"version": VERSION}).encode(), OPEN)
        elif url.path == "/targets":               # where a typed reply goes
            body = {"twitch": TWITCH, "youtube_video": state["youtube_video"], "tiktok": TIKTOK, "facebook": FACEBOOK,
                    "instagram": INSTAGRAM, "rumble_chat": state.get("rumble_chat") or "", "live": streaming.is_set(),
                    "tiktok_joins": bool(FILTERS.get("joins"))}
            await reply(writer, "200 OK", "application/json", json.dumps(body).encode())
        elif url.path == "/events":
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-store\r\n" + OPEN.encode()
                         + b"Connection: keep-alive\r\n\r\nretry: 2000\n\n")
            outsider = not remote and (overlay_address(headers) or from_elsewhere(headers))
            queue = PublicFeed() if outsider else asyncio.Queue()
            for old in list(messages):
                queue.put_nowait(old)
            for event in (status_event(), viewer_event(), {"type": "feature", "msg": state["featured"]},
                          {"type": "starred", "ids": list(starred)}, {"type": "quick", "replies": quick_replies()}, twitch_event(),
                          kick_event(), rumble_event(), discord_event(), {"type": "emotes", "emotes": EMOTES}, {"type": "tts", "settings": TTS},
                          {"type": "filters", "settings": FILTERS}):
                queue.put_nowait(event)
            clients.add(queue)
            if not remote and not outsider:
                local_clients.add(queue)
                queue.put_nowait(devices_event())
                queue.put_nowait(companion_event())
                queue.put_nowait(update_event())
                if query.get("executor") == ["1"]:           # the chat window with the extension: it posts for everyone
                    take_role("executor", queue)
                    send(executor_event())
                    spawn(chat_connected())                 # (and puts itself in its place, if CrossChat has just opened it)
                if query.get("speaker") == ["1"]:            # the chat window on this PC (not in OBS): it reads chat aloud
                    take_role("speaker", queue)
            queue.put_nowait(executor_event())        # (not to a PublicFeed)
            try:
                while True:
                    try:                   # the executor is checked often, so paired devices soon learn it has gone
                        event = await asyncio.wait_for(queue.get(), 5 if state["executor"] is queue else 15)
                        writer.write(("data: " + json.dumps(event) + "\n\n").encode())
                    except asyncio.TimeoutError:
                        writer.write(b": still here\n\n")
                    await writer.drain()
            finally:
                clients.discard(queue)
                local_clients.discard(queue)
                if drop_role("executor", queue):
                    send(executor_event())
                drop_role("speaker", queue)
        elif url.path == "/show":
            await show_window()
            await reply(writer, "200 OK", "text/plain", b"ok")
        elif url.path == "/stream":                # Start stream / End stream, when CrossChat follows no streaming app
            answer = await manual_stream((query.get("go") or [""])[0])
            await reply(writer, "200 OK", TYPES[".json"], json.dumps(answer).encode())
        elif url.path == "/leave":                 # Close CrossChat (the modes that don't end when OBS closes)
            leaving = state.get("leave")
            if leaving:
                leaving.set()
            await reply(writer, "200 OK", TYPES[".json"], json.dumps({"ok": bool(leaving)}).encode())
        elif url.path == "/x/go":                  # Go live on X (OBS script button, hotkey or shortcut), or a test
            mode = (query.get("mode") or ["live"])[0]
            did = await x_go(mode if mode in ("live", "private", "dry") else "live")
            await reply(writer, "200 OK", "text/plain", did.encode())
        elif url.path == "/x/state":               # the extension asks: may I, and with what title?
            armed = state.get("x_armed")
            go = armed[0] if armed and time.time() - armed[1] < 120 else ""
            state["x_armed"] = None                # one use only
            body = {"go": go, "title": x_title(), "source": X.get("source", "OBS"), "post": X.get("post", "")}
            await reply(writer, "200 OK", "application/json", json.dumps(body).encode())
        elif url.path == "/x/result":              # the extension reports how it went
            first = lambda k: (query.get(k) or [""])[0]
            x_result(first("ok") == "1", re.sub(r"[^a-z]", "", first("mode"))[:10], re.sub(r"[^\w .:-]", "", first("step"))[:80])
            await reply(writer, "200 OK", "application/json", b"{}")
        elif url.path == "/x/feed":                # the extension passes on X's own viewer count and chat lines
            x_feed(lambda k: (query.get(k) or [""])[0])
            # the answer tells the page when OBS has stopped, so it can end the livestream on X too
            await reply(writer, "200 OK", "application/json", json.dumps({"end": bool(state.get("x_end"))}).encode())
        elif url.path in PAGE_FEEDS:               # the extension passes on the chat shown on a platform's own page
            mine = PAGE_FEEDS[url.path].feed(lambda k: (query.get(k) or [""])[0])
            await reply(writer, "200 OK", "application/json", json.dumps({"mine": mine}).encode())
        else:
            await reply(writer, "404 Not Found", "text/plain", b"not found")
    except FileNotFoundError:
        await reply(writer, "404 Not Found", "text/plain", b"not found")
    except (OSError, asyncio.TimeoutError, ConnectionError):
        pass
    finally:
        if remote:
            remote_open -= 1
        try:
            writer.close()
        except OSError:
            pass


async def serve_post(reader, writer, headers, path, remote=False):
    """The Theme Studio's, the chat window's and paired devices' changes, as JSON."""
    global TTS, FILTERS
    try:
        size = int(headers.get("content-length", "0"))
    except ValueError:
        size = -1
    if not 0 <= size <= BODY_LIMIT:
        await reply(writer, "413 Payload Too Large", "text/plain", b"too big")
        return
    try:
        body = json.loads((await asyncio.wait_for(reader.readexactly(size), 10)).decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError, asyncio.IncompleteReadError):
        body = None
    if not isinstance(body, dict):
        await reply(writer, "400 Bad Request", "text/plain", b"not a JSON object")
        return
    extra = ""
    if path == "/pair" and remote:
        token = pair_device(str(body.get("code") or ""), headers)
        result = {"ok": bool(token)} if token else {"ok": False, "why": "That code did not work. Check it, or start pairing again on the streaming PC."}
        extra = device_cookie(token) if token else ""
    elif path == "/send":
        result = new_send(body)
    elif path == "/mod":
        result = new_mod(body)
    elif path == "/feature":
        result = {"ok": feature(str(body.get("id") or ""))}
    elif path == "/star":
        set_star(str(body.get("id") or ""), bool(body.get("on")))
        result = {"ok": True}
    elif path == "/quick":
        replies = body.get("replies")
        if not isinstance(replies, list) or len(replies) > 30 or any(not isinstance(r, str) or not r.strip() or len(r) > 100 for r in replies):
            result = {"ok": False, "why": "Quick replies are up to 30 lines of up to 100 characters."}
        else:
            config_file.replace_file(quick_path(), json.dumps([" ".join(r.split()) for r in replies], ensure_ascii=False, indent=1))
            send({"type": "quick", "replies": quick_replies()})
            result = {"ok": True}
    elif path == "/outbox/result" and not remote:          # the executor's answer to a job
        future = jobs.get(str(body.get("job_id") or ""))
        if future and not future.done():
            future.set_result(body.get("answer") if isinstance(body.get("answer"), dict) else {})
        result = {"ok": bool(future)}
    elif path in ("/kick/connect", "/kick/disconnect", "/twitch/connect", "/twitch/disconnect", "/devices/revoke", "/rumble/connect",
                  "/rumble/disconnect", "/discord/connect", "/discord/options", "/discord/test", "/discord/disconnect",
                  "/companion/tailscale") and DEMO:
        result = {"ok": False, "why": "The demo never touches your real accounts or devices."}
    elif path == "/pair/start" and DEMO:
        result = {"ok": False, "why": "Pairing is switched off in the demo."}
    elif path == "/config" and DEMO:
        result = {"ok": False, "why": "The demo doesn't change your settings."}
    elif path == "/config" and not remote:              # Settings → Channels & options: checked, saved, applied
        result, changes = settings_ui.save(CONFIG_PATH, body, CFG, channel, PORT)
        if changes:
            settings_ui.apply_live(sys.modules[__name__], changes)
            send({"type": "config", **settings_ui.editable(CFG)}, only=local_clients)
    elif path == "/pair/start" and not remote:
        code, expires = DEV.start_pairing()
        await remote_on()
        url = tailscale_url() or lan_url()         # Tailscale's address works at home and away
        result = {"ok": bool(remote_server or tailscale_server), "code": code, "url": (url + "pair?code=" + code) if url else None,
                  "expires": int(expires)}
        if not result["ok"]:
            result["why"] = (" ".join(w for w in (remote_why, tailscale_why if tailscale_wanted() else "") if w)
                             or "The companion is switched off in config.json (\"remote\": {\"enabled\"}).")
        send({"type": "pair", **result}, only=local_clients)
    elif path == "/devices/revoke" and not remote:
        result = {"ok": DEV.revoke(str(body.get("id") or ""))}
        send(devices_event(), only=local_clients)
        if not DEV.devices and not DEV.pairing_open():
            await remote_off()                     # nothing left to answer
    elif path == "/twitch/connect" and not remote:
        if not TW.client_id:
            result = {"ok": False, "why": "This CrossChat has no Twitch app Client ID (\"twitch_client_id\" in config.json)."}
        else:
            spawn(twitch_connect())
            result = {"ok": True}
    elif path == "/tts" and not remote:
        try:
            TTS = clean_tts(body.get("settings") if isinstance(body.get("settings"), dict) else body)
            config_file.replace_file(settings_path("tts.json"), json.dumps(TTS, indent=1))
            send({"type": "tts", "settings": TTS})
            result = {"ok": True}
        except (TypeError, ValueError) as error:
            result = {"ok": False, "why": "Those text-to-speech settings don't work: %s" % error}
    elif path == "/tts/say":
        found = next((m for m in reversed(messages) if m["id"] == str(body.get("id") or "")), None)
        text = speech(found, force=True) if found and not found.get("hidden") else ""
        result = {"ok": bool(text and state.get("speaker") is not None)}
        if not text:
            result["why"] = "That message is too old, hidden by your filters, or has nothing to read."
        elif state.get("speaker") is None:
            result["why"] = "Open the CrossChat window on the streaming PC: it does the talking."
        else:
            say(text, found["id"])
    elif path == "/tts/skip":
        if state.get("speaker") is not None:
            send({"type": "say_stop"}, only=[state["speaker"]])
        result = {"ok": True}
    elif path == "/filters" and not remote:
        try:
            FILTERS = clean_filters(body.get("settings") if isinstance(body.get("settings"), dict) else body)
            config_file.replace_file(settings_path("filters.json"), json.dumps(FILTERS, indent=1, ensure_ascii=False))
            send({"type": "filters", "settings": FILTERS})
            hide_earlier()
            result = {"ok": True}
        except ValueError as error:
            result = {"ok": False, "why": str(error)}
    elif path == "/rumble/connect" and not remote:
        try:
            await asyncio.to_thread(RB.set, body.get("url"))         # (a thread: the keyring may ask to be unlocked first)
            result = {"ok": True}
            if streaming.is_set():
                set_status("rumble", "waiting")
        except RumbleError as error:
            result = {"ok": False, "why": str(error)}
        except OSError as error:
            result = {"ok": False, "why": not_saved(error)}
        send(rumble_event())
    elif path == "/rumble/disconnect" and not remote:
        RB.forget()
        status.pop("rumble", None)
        viewers.pop("rumble", None)
        send(rumble_event())
        send(status_event())
        result = {"ok": True}
    elif path == "/discord/connect" and not remote:
        try:
            await asyncio.to_thread(DC.set, body.get("url"), body)
            result = {"ok": True}
        except DiscordError as error:
            result = {"ok": False, "why": str(error)}
        except OSError as error:
            result = {"ok": False, "why": not_saved(error)}
        send(discord_event())
    elif path == "/discord/options" and not remote:
        try:
            await asyncio.to_thread(DC.choose, body)
            result = {"ok": True}
        except OSError as error:
            result = {"ok": False, "why": not_saved(error)}
        send(discord_event())
    elif path == "/discord/test" and not remote:
        try:
            await asyncio.to_thread(DC.post, {"content": HELLO, "allowed_mentions": {"parse": []}, "flags": SUPPRESS_NOTIFICATIONS})
            result = {"ok": True}
        except DiscordError as error:
            result = {"ok": False, "why": str(error)}
        send(discord_event())
    elif path == "/discord/disconnect" and not remote:
        DC.forget()
        send(discord_event())
        result = {"ok": True}
    elif path == "/companion/tailscale" and not remote:
        try:
            save_setting("remote.tailscale", body.get("on") is True)
            result = {"ok": True}
        except (OSError, ValueError) as error:
            result = {"ok": False, "why": str(error) if isinstance(error, ValueError) else "Could not write config.json."}
        if tailscale_wanted():
            await tailscale_on()
        else:
            await tailscale_off()
        send(companion_event(), only=local_clients)
    elif path == "/updates" and not remote:
        try:
            save_setting("updates.check", body.get("check") is True)
            result = {"ok": True}
        except (OSError, ValueError) as error:
            result = {"ok": False, "why": str(error) if isinstance(error, ValueError) else "Could not write config.json."}
        if update_state["wake"]:
            update_state["wake"].set()           # switched on: ask GitHub now (unless it was asked in the last day)
        send(update_event(), only=local_clients)
    elif path == "/kick/connect" and not remote:
        if not KK.client_id:
            result = {"ok": False, "why": "This CrossChat has no Kick app (\"kick_client_id\" in config.json)."}
        else:
            url = KK.start()
            send(kick_event())
            result = {"ok": True, "url": url}
    elif path == "/kick/disconnect" and not remote:
        result = signed_out("Kick", await asyncio.to_thread(KK.forget), "kick.com, in your account settings")
        send(kick_event())
    elif path == "/twitch/disconnect" and not remote:
        result = signed_out("Twitch", await asyncio.to_thread(TW.forget), "https://www.twitch.tv/settings/connections")
        send(twitch_event())
    elif path in ("/themes/save", "/themes/delete", "/themes/default"):
        try:
            result = theme_change(body, path[8:])
        except OSError as error:
            result = {"ok": False, "why": "Could not write the theme file: %s" % error.strerror}
    elif path == "/test":
        result = {"ok": True}
        kind = str(body.get("kind") or "")
        if kind in ("chat", "alert", "featured", "viewers"):
            spawn(test_event(kind))
        else:
            result = {"ok": False, "why": "unknown test"}
    else:
        await reply(writer, "404 Not Found", "text/plain", b"not found")
        return
    await reply(writer, "200 OK", TYPES[".json"], json.dumps(result).encode(), extra)


def start_log():
    path = arg("--log", os.path.join(HOME, "crosschat-demo.log" if DEMO else "crosschat.log"))
    try:
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=512 * 1024, backupCount=1, encoding="utf-8")
    except OSError:
        handler = logging.NullHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()                   # the root, so asyncio's and the libraries' errors land here too: under pythonw nothing else shows them
    root.addHandler(handler)
    if TEST and sys.stderr:
        root.addHandler(logging.StreamHandler())
    log.setLevel(logging.INFO)
    for text in problems:                        # what configure found, now that there's a log to tell
        log.warning(text)


def loop_problem(loop, context):
    """Whatever the event loop can't hand back to anyone (a request's job that failed, say): in the log, where it can be found."""
    log.error("unexpected: %s", context.get("message", "no details"), exc_info=context.get("exception"))


def companion_setup():
    """Paired devices and the Twitch connection, kept in your folder."""
    global DEV, TW, KK, RB, DC, LOG, FILTERS, TTS
    DEV = Devices(settings_path("devices.json"), trouble)
    TW = Twitch(CFG.get("twitch_client_id") or TWITCH_CLIENT_ID, os.path.join(HOME, "twitch.bin"))
    own = bool(CFG.get("kick_client_id"))            # your own Kick app replaces CrossChat's, id and secret together
    KK = Kick(CFG["kick_client_id"] if own else KICK_CLIENT_ID, CFG.get("kick_client_secret", "") if own else KICK_CLIENT_SECRET,
              os.path.join(HOME, "kick.bin"), "http://localhost:%d/kick/callback" % PORT)
    RB = Rumble(os.path.join(HOME, "rumble.bin"))
    DC = Discord(os.path.join(HOME, "discord.bin"), NAMES, changed=lambda: send(discord_event()))
    LOG = ChatLog(os.path.join(HOME, "logs"), int((CFG.get("logs") or {}).get("keep_days") or 90), warn)
    FILTERS = settings_file("filters.json", FILTER_DEFAULTS, clean_filters, "your chat filters")
    TTS = settings_file("tts.json", TTS_DEFAULTS, clean_tts, "your text-to-speech settings")


ALREADY_RUNNING = 3                          # the exit code that says so: the OBS script's watchdog then starts no hub of its own
PORT_TAKEN = 4                               # another program has the port: the streamer has been told, and starting again wouldn't help
ready = None                                 # set once companion_setup is done (main makes it); requests but /version wait for it


def other_hub_answers():
    """Whether what holds our port is a CrossChat hub: only one answers /version like this."""
    with requests.Session() as direct:
        direct.trust_env = False                 # (this PC asking itself: never through a proxy)
        try:
            return isinstance(direct.get("http://127.0.0.1:%d/version" % PORT, timeout=5).json().get("version"), str)
        except (requests.RequestException, ValueError, AttributeError):
            return False


async def main():
    global ready
    asyncio.get_running_loop().set_exception_handler(loop_problem)
    try:
        server = await asyncio.start_server(serve, "127.0.0.1", PORT)
    except OSError as error:
        if await asyncio.to_thread(other_hub_answers):
            log.info("port %d is taken: another CrossChat hub is already running", PORT)
            return ALREADY_RUNNING
        box = warn("CrossChat can't use port %d (%s), so it can't run. Close the program that is using it, then start CrossChat again."
                   % (PORT, error.strerror or error))
        if box:
            await asyncio.to_thread(box.join)    # (leaving now would take the message box with it)
        return PORT_TAKEN
    ready = asyncio.Event()
    await asyncio.to_thread(companion_setup)     # (a locked keyring can take its time: chat and the pages must not wait for it)
    ready.set()
    for text in problems:
        warn(text, logged=True)
    problems.clear()
    if PORT != DEFAULTS["port"] and not DEMO:
        warn("CrossChat is on port %d, but the browser extension only talks to %d: replies, going live on X and the TikTok, Facebook and "
             "Instagram chats need it, and so does Connect Kick. Remove \"port\" from config.json to use them." % (PORT, DEFAULTS["port"]))
    if not DEMO:                                 # the demo stays on this PC
        await remote_on()
    log.info("CrossChat %s on http://127.0.0.1:%d (Twitch %r, YouTube %r, Kick %r, X %s; Python %s in %s)", VERSION, PORT, TWITCH, YOUTUBE,
             KICK, "on" if X else "off", sys.version.split()[0], sys.prefix)
    tasks = []
    for name, wanted, job in (("twitch", TWITCH, lambda: twitch(TWITCH)), ("youtube", YOUTUBE, lambda: youtube(YOUTUBE)),
                              ("kick", KICK, lambda: kick(KICK, KICK_ROOM))):
        if wanted and not DEMO:                  # the demo never mixes in real chat
            status[name] = "off"
            tasks.append(asyncio.create_task(keep_running(name, job)))
    if X:
        status["x"] = "off"
    for chat in PAGE_CHATS:
        if chat.wanted() and not DEMO:
            status[chat.name] = "off"
    if (X or any(chat.wanted() for chat in PAGE_CHATS)) and not DEMO:     # (the demo has no pages to wait for)
        tasks.append(asyncio.create_task(keep_running("pages", x_watch)))
    if RB and RB.on() and not DEMO:
        status["rumble"] = "off"
    tasks.append(asyncio.create_task(keep_running("rumble", rumble_watch)))
    tasks.append(asyncio.create_task(keep_running("viewers", demo_stream if DEMO else audience)))
    tasks.append(asyncio.create_task(keep_running("emotes", emotes_refresh)))
    if not DEMO:
        tasks.append(asyncio.create_task(keep_running("companion", remote_watch)))
        tasks.append(asyncio.create_task(keep_running("discord", DC.run)))
        tasks.append(asyncio.create_task(keep_running("updates", update_watch)))
    try:
        if TEST:
            await stream_started()
            await asyncio.Event().wait()
        else:
            await keep_running("obs", follow_app)
    finally:
        # Stop listening, without waiting for the open connections to end ("async with server" does, from Python
        # 3.12.1): a chat page's live feed never ends by itself, so a chat still open in a tab kept the hub (and its
        # port) after OBS had closed.
        server.close()
    for t in tasks:
        t.cancel()


if __name__ == "__main__":
    configure(sys.argv[1:])
    start_log()
    try:
        sys.exit(asyncio.run(main()))
    except Exception:
        log.exception("CrossChat stopped on something unexpected")
        sys.exit(1)
