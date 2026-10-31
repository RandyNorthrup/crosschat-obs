"""CrossChat hub: the chat of every platform the stream goes to, in one window, following OBS.

OBS starts this (obs/crosschat.lua) and it leaves when OBS closes. When OBS starts streaming it opens the chat
window; it closes the window a little while after the stream ends. With the CrossChat browser extension it also
starts and ends the livestream on X and posts the replies typed in the chat window.

Settings are in config.json in the folder above this one (see config.example.json).

  python hub.py --test [--twitch NAME] [--youtube @HANDLE_OR_CHANNEL_ID] [--kick SLUG[:CHATROOM_ID]]
      run without OBS, as if a stream had just started (for trying it against any public channel)
  python hub.py --config PATH      another settings file
  python hub.py --obs-config DIR   OBS's settings folder (the OBS script passes it, so portable OBS works too)
  python hub.py --obs-pid PID      stay until that OBS closes (the OBS script passes it)
  python hub.py --quiet            no message boxes, only the log
"""
import asyncio
import collections
import ctypes
import base64
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
from ctypes import wintypes

import requests
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

from devices import Devices, device_name
from twitch_api import Twitch, TwitchError

VERSION = "1.2.0"
# CrossChat's public Twitch app (Client ID only: public apps have no secret). "twitch_client_id" in config.json overrides it.
TWITCH_CLIENT_ID = "gg5cmjfvr1l09niyes19ccclashuth"  # gitleaks:allow (a public client ID, not a secret)
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
    "browser": "auto",                       # "auto" (Chrome, else Edge), "chrome", "edge" or the full path of a browser
    "window": "auto",                        # "auto" (right edge of the main screen) or {"x", "y", "width", "height"}
    "open_window_on_stream_start": True,
    "close_window_seconds_after_stream": 120,
    "overlay": {"platforms": "all", "theme": "classic"},
    "obs": {"host": "127.0.0.1", "port": 0, "password": ""},     # port 0 and no password: read from OBS's own settings
    "remote": {"enabled": True, "port": 4467},                  # the companion for paired devices on the home network
    "twitch_client_id": "",
    "custom_overlays": "",                   # a folder of your own overlay pages, served at /custom/ (see custom_file)
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
TEST, PORT = False, DEFAULTS["port"]
TWITCH = YOUTUBE = KICK = ""
KICK_ROOM = 0


def arg(name, default):
    return ARGV[ARGV.index(name) + 1] if name in ARGV[:-1] else default


def merged(base, over):
    """`over` laid on top of `base`, one level of nested sections deep."""
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
    value = re.sub(r"^(?:https?://)?(?:www\.)?(?:twitch\.tv|kick\.com)/", "", value, flags=re.I)
    value = re.split(r"[/?#]", value)[0].lower().lstrip("@")
    pattern = r"[a-z0-9_]{1,25}" if platform == "twitch" else r"[a-z0-9_-]{1,40}"
    return value if re.fullmatch(pattern, value) else ""


def configure(argv):
    """Settings: the defaults, then config.json (or --config PATH, or the file CROSSCHAT_CONFIG names), then the command line."""
    global ARGV, CFG, X, HOME, TEST, PORT, TWITCH, YOUTUBE, KICK, KICK_ROOM
    ARGV = list(argv)
    path = os.path.abspath(arg("--config", os.environ.get("CROSSCHAT_CONFIG") or os.path.join(APP, "config.json")))
    HOME = os.path.dirname(path)
    try:
        with open(path, encoding="utf-8-sig") as f:
            mine = json.load(f)
    except FileNotFoundError:
        mine = {}
    except (OSError, ValueError) as error:
        log.error("config.json could not be read (%s); the defaults are used", error)
        mine = {}
    CFG = merged(DEFAULTS, mine if isinstance(mine, dict) else {})
    X = CFG["x"] if CFG["x"].get("enabled") else {}
    TEST = "--test" in ARGV
    PORT = int(arg("--port", CFG["port"]))
    TWITCH = channel(arg("--twitch", CFG["twitch"]), "twitch")
    YOUTUBE = channel(arg("--youtube", CFG["youtube"]), "youtube")
    KICK, KICK_ROOM = channel(CFG["kick"], "kick"), int(CFG["kick_chatroom"] or 0)
    if "--kick" in ARGV:
        slug, _, room = arg("--kick", "").partition(":")
        KICK, KICK_ROOM = channel(slug, "kick"), int(room or 0)
    for name, given, used in (("twitch", CFG["twitch"], TWITCH), ("youtube", CFG["youtube"], YOUTUBE), ("kick", CFG["kick"], KICK)):
        if given and not used:
            log.warning("config.json: %r is not a %s channel I can use; leaving %s out", given, name, name)


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
    for q in list(only if only is not None else clients):
        q.put_nowait(event)


def publish(platform, name, text, color="", badges=(), mid="", kind="chat", raw="", **more):
    """raw: the platform's own message id (for moderating it). more: emotes (Twitch's "id:from-to,..." list), handle
    (the @name on X), uid (the platform's user id), alert, amount, system and test, for the pages that use them."""
    event = {"type": "msg", "id": mid or "%s-%d" % (platform, time.time_ns()), "t": int(time.time() * 1000),
             "p": platform, "name": name, "text": text, "color": color, "badges": list(badges), "kind": kind}
    event.update({k: v for k, v in more.items() if v})
    if raw:
        event["mid"] = raw
    if kind == "chat" and len(text) > 6 and QUESTION.search(text):
        event["question"] = True
    messages.append(event)
    send(event)


def status_event():
    return {"type": "status", "status": dict(status), "live": streaming.is_set(), "yt": state["youtube_video"]}


def set_status(platform, value):
    if status.get(platform) != value:
        status[platform] = value
        log.info("%s chat: %s", platform, value)
        send(status_event())


def note(text):
    publish("system", "", text, kind="note")


def warn(text):
    """Tell the person at the PC: in the log, in the chat window and once in a plain Windows message box (the hub has
    no window of its own, so a problem would otherwise go unseen)."""
    log.warning(text)
    note(text)
    if "--quiet" not in ARGV:
        threading.Thread(target=user32.MessageBoxW, args=(None, text, "CrossChat", 0x30 | 0x10000 | 0x40000), daemon=True).start()


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
    return alert, tags.get(count, "") if count else ""


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
                tags = {}
                if line.startswith("@"):
                    raw, _, line = line[1:].partition(" ")
                    tags = irc_tags(raw)
                parts = line.split(" ", 3)
                command = parts[1] if len(parts) > 1 else ""
                if command in ("366", "ROOMSTATE"):          # joined
                    set_status("twitch", "on")
                    wait = 2
                elif command == "PRIVMSG" and len(parts) == 4:
                    text = parts[3][1:]
                    emotes = tags.get("emotes", "")
                    if text.startswith("\x01ACTION "):
                        text, emotes = text[8:].rstrip("\x01"), ""      # emote positions count from the full line
                    badges = [b.split("/")[0] for b in tags.get("badges", "").split(",") if b]
                    name = tags.get("display-name") or parts[0][1:].split("!")[0]
                    publish("twitch", name, text, tags.get("color", ""), badges, "tw-" + tags.get("id", ""), emotes=emotes,
                            raw=tags.get("id", ""), uid=tags.get("user-id", ""))
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
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError):
            pass
        finally:
            if writer:
                writer.close()
        set_status("twitch", "retry")
        await asyncio.sleep(wait)
        wait = min(wait * 2, 60)


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


def yt_open(video):
    html = web.get("https://www.youtube.com/live_chat?is_popout=1&v=" + video, timeout=15).text
    key = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html)
    version = re.search(r'"(?:INNERTUBE_CLIENT_VERSION|clientVersion)":"([^"]+)"', html)
    data = page_json(html, "ytInitialData")
    chat = ((data or {}).get("contents") or {}).get("liveChatRenderer")
    if not (key and version and chat):
        return None
    token = next(iter(chat["continuations"][0].values()))["continuation"]
    try:      # the second entry of the menu is "Live chat": every message, not only "Top chat"
        menu = chat["header"]["liveChatHeaderRenderer"]["viewSelector"]["sortFilterSubMenuRenderer"]["subMenuItems"]
        token = menu[1]["continuation"]["reloadContinuationData"]["continuation"]
    except (KeyError, IndexError):
        pass
    return {"key": key.group(1), "version": version.group(1), "token": token}


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
                amount = (re.search(r"\d+", system) or [""])[0]
            event = {"type": "msg", "id": "yt-" + r.get("id", ""), "name": yt_text(r.get("authorName")),
                     "text": text, "badges": badges, "usec": int(r.get("timestampUsec", 0)), "kind": "event" if YT_KINDS[kind] else "chat",
                     "uid": r.get("authorExternalChannelId", "")}
            if YT_KINDS[kind]:
                event.update(alert=YT_KINDS[kind], amount=amount, system=system.strip())
            events.append(event)
    return events, min(max(nxt.get("timeoutMs", 5000) / 1000, 1.5), 8)


async def youtube(target):
    seen = collections.deque(maxlen=2000)
    while True:
        await streaming.wait()
        set_status("youtube", "waiting")
        began, video = time.time(), ""
        while streaming.is_set() and not video:       # YouTube takes a little while to notice the stream
            try:
                video = await asyncio.to_thread(yt_live_video, target)
            except (requests.RequestException, ValueError):
                video = ""
            if not video:
                await asyncio.sleep(10 if time.time() - began < 300 else 30)
        chat = None
        while streaming.is_set() and video and not chat:
            try:
                chat = await asyncio.to_thread(yt_open, video)
            except (requests.RequestException, ValueError, KeyError):
                chat = None
            if not chat:
                await asyncio.sleep(15)
        if not chat:
            set_status("youtube", "off")
            continue
        state["youtube_video"], state["youtube_chat"] = video, chat
        set_status("youtube", "on")
        failures = 0
        while streaming.is_set() and failures < 6:
            try:
                result = await asyncio.to_thread(yt_poll, chat)
            except (requests.RequestException, ValueError, KeyError):
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
        return name, "%s gifted %d sub%s" % (name, count, "" if count == 1 else "s"), "gift", str(count)
    if event.endswith("StreamHostEvent"):
        name, count = d.get("host_username") or "Someone", str(d.get("number_viewers") or 0)
        return name, "%s is raiding with %s viewers" % (name, count), "raid", count
    name, months = d.get("username") or "Someone", str(d.get("months") or 1)
    if months.isdigit() and int(months) > 1:
        return name, "%s subscribed for %s months" % (name, months), "resub", months
    return name, "%s subscribed" % name, "sub", ""


async def kick(slug, room):
    while not room:                               # the chat room number comes from the channel's public record
        try:
            found = await asyncio.to_thread(requests.get, "https://kick.com/api/v2/channels/" + slug, headers=UA, timeout=12)
            room = (found.json().get("chatroom") or {}).get("id", 0) if found.status_code == 200 else 0
        except (requests.RequestException, ValueError):
            room = 0
        if not room:
            set_status("kick", "retry")
            await asyncio.sleep(60)
    url = CFG.get("kick_feed", "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=8.4.0&flash=false")
    wait = 2
    while True:
        try:
            set_status("kick", "waiting")
            async with connect(url, open_timeout=20, ping_interval=None) as ws:
                await ws.send(json.dumps({"event": "pusher:subscribe", "data": {"auth": "", "channel": "chatrooms.%d.v2" % room}}))
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), 100)
                    except asyncio.TimeoutError:
                        await ws.send('{"event":"pusher:ping","data":{}}')
                        continue
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
        except Exception:        # any drop: wait and reconnect
            pass
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


def viewer_event():
    return {"type": "viewers", "counts": dict(viewers), "total": sum(v for v in viewers.values() if v)}


async def audience():
    sources = [(name, job) for name, wanted, job in (("twitch", TWITCH, lambda: twitch_viewers(TWITCH)),
               ("youtube", YOUTUBE, youtube_viewers), ("kick", KICK, lambda: kick_viewers(KICK))) if wanted]
    while True:
        await streaming.wait()
        fresh = time.time() - state["since"] < 120
        for name, job in sources:
            try:
                viewers[name] = await asyncio.to_thread(job)
            except Exception:                   # a failed lookup just shows as unknown
                viewers[name] = None
        send(viewer_event())
        await asyncio.sleep(10 if fresh else 30)


# ---- the windows: plain browser windows parked at the edge of the screen ---------------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenProcess.restype = wintypes.HANDLE
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except (AttributeError, OSError):
    pass


def browser_windows(prefix=None):
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
    area = wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0)      # SPI_GETWORKAREA
    return area.left, area.top, area.right, area.bottom


def box(setting, part):
    """(x, y, width, height) for the chat window (part "chat") or X's page (part "x"): the setting when it is a
    rectangle, else a strip at the right edge of the main screen, the chat on top and X's page under it."""
    if isinstance(setting, dict) and all(isinstance(setting.get(k), int) for k in ("x", "y", "width", "height")):
        return setting["x"], setting["y"], setting["width"], setting["height"]
    left, top, right, bottom = work_area()
    width = min(460, max(320, (right - left) // 4))
    split = top + (bottom - top) * 3 // 5 if X else bottom
    return (right - width, top, width, split - top) if part == "chat" else (right - width, split, width, bottom - split)


def browser_exe():
    """The browser the windows open in: "browser" in config.json is "auto" (Chrome, else Edge), "chrome", "edge" or a path.

    It has to be the everyday browser, because that is where the logins and the CrossChat extension live.
    """
    want = str(CFG.get("browser") or "auto")
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


async def open_app(url, where):
    """Open a bare window of the everyday browser on `url` at `where` (x, y, width, height) and hand the keyboard back."""
    exe = browser_exe()
    if not exe:
        warn("CrossChat could not find Chrome or Edge. Set \"browser\" in config.json to the full path of your browser.")
        return None
    before, front = set(browser_windows()), user32.GetForegroundWindow()
    cmd = [exe, "--app=" + url, "--window-position=%d,%d" % where[:2], "--window-size=%d,%d" % where[2:]]
    subprocess.Popen(cmd, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        await asyncio.sleep(0.25)
        new = [h for h in browser_windows() if h not in before]
        if new:
            place(new[0], *where)
            if front:
                user32.SetForegroundWindow(front)
            return new[0]
    return None


async def show_window():
    where = box(CFG["window"], "chat")
    found = browser_windows(TITLE)
    if found:
        place(found[0], *where)
    else:
        await open_app("http://127.0.0.1:%d/" % PORT, where)


def close_window():
    for hwnd in browser_windows(TITLE):
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


def close_x_window():
    hwnd = state.get("x_window")
    if hwnd and user32.IsWindow(wintypes.HWND(hwnd)):
        user32.PostMessageW(wintypes.HWND(hwnd), 0x0010, 0, 0)
    state["x_window"] = None


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
    state["x_last"] = None
    close_x_window()
    state["x_window"] = await open_app("https://studio.x.com/live" + tail, box(X.get("window"), "x"))
    if mode == "live":
        note("X: starting the livestream there...")
    return mode or "OBS is not live, so X was only opened"


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


async def x_watch():
    """X counts as live only while its page keeps reporting in."""
    while True:
        await asyncio.sleep(5)
        if time.time() - state.get("x_seen", 0) > 20:
            x_off()


def x_result(ok, mode, step):
    state["x_last"] = {"ok": ok, "mode": mode, "step": step, "at": time.time()}
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
    messages.clear()
    x_told.clear()
    streaming.set()
    send({"type": "clear"})
    send(status_event())
    note("Test stream to this PC only." if local else "Stream started. Chat from every platform shows up here.")
    if CFG.get("open_window_on_stream_start", True) and "--no-window" not in ARGV:
        await show_window()
    if X.get("auto_go_live") and not local and not TEST:
        async def soon():                       # give X a moment to see the video arriving
            await asyncio.sleep(X.get("delay_seconds", 12))
            if streaming.is_set():
                await x_go("live")
        asyncio.create_task(soon())


async def stream_stopped():
    global closing
    if not streaming.is_set():
        return
    log.info("stream stopped")
    streaming.clear()
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
        asyncio.create_task(end_x())

    async def later():
        await asyncio.sleep(CFG.get("close_window_seconds_after_stream", 120))
        close_window()
        close_x_window()
    closing = asyncio.create_task(later())


# ---- OBS: its WebSocket server tells the hub when the stream starts and stops ----------------------
def obs_settings():
    """Where OBS's WebSocket server listens and its password: config.json's "obs" section first, else OBS's own
    settings (in the folder the OBS script passes with --obs-config, or the usual one under %APPDATA%)."""
    folder = arg("--obs-config", "") or os.path.expandvars(r"%APPDATA%\obs-studio")
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


async def obs_link():
    """Follow OBS until it closes. With --obs-pid that is the OBS process ending; started by hand, it is the
    connection ending (or a minute and a half without one)."""
    pid = int(arg("--obs-pid", "0") or 0)
    tries, told = 0, set()
    while obs_open(pid) if pid else tries < 30:
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
            while obs_open(pid):
                await asyncio.sleep(2)
            await link.close()
        watcher = asyncio.create_task(gone(ws)) if pid else None
        try:
            async with ws:
                await obs_session(ws, where["password"])
        except ConnectionClosed as closed:
            if closed.rcvd and closed.rcvd.code == 4009 and "password" not in told:     # AuthenticationFailed
                told.add("password")
                warn("OBS refused CrossChat's WebSocket password. Leave \"password\" in config.json empty so CrossChat "
                     "reads it from OBS, or copy it from Tools > WebSocket Server Settings > Show Connect Info.")
                await asyncio.sleep(RETRY_AFTER_REFUSAL)
        except (OSError, ValueError, KeyError) as error:
            log.warning("OBS connection: %s", error)
        finally:
            if watcher:
                watcher.cancel()
        if not pid:
            break
        await asyncio.sleep(2)
    log.info("OBS closed")
    close_window()
    close_x_window()


# ---- themes: how the on-stream widgets look ----------------------------------------------------------
# The ones that come with CrossChat are in hub/presets and can't be changed; yours are in themes/ in the CrossChat
# folder, one JSON file each, made in the Theme Studio (/studio).
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


def write_file(path, text):
    """Replace a file in one step, so a crash can't leave half a theme."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(path + ".tmp", path)


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
        write_file(os.path.join(themes_dir(), "default.txt"), name)
    elif builtin:
        return {"ok": False, "why": "%s comes with CrossChat and can't be changed. Save it under a new name." % name}
    elif what == "save":
        theme = body.get("theme")
        text = json.dumps(theme, indent=2, ensure_ascii=False)
        if not isinstance(theme, dict) or len(text.encode()) > 64 * 1024:
            return {"ok": False, "why": "A theme is a JSON object of at most 64 KB."}
        write_file(mine, text + "\n")
    elif os.path.isfile(mine):
        os.remove(mine)
    log.info("theme %s: %s", what, name)
    send({"type": "theme", "name": name, "default": default_theme()})
    return {"ok": True}


# ---- the featured message and test events -------------------------------------------------------------
def feature(mid):
    """Show one message big on stream (the featured-message widget), or nothing when `mid` is ''."""
    found = next((m for m in reversed(messages) if m["id"] == mid and m["kind"] in ("chat", "event")), None) if mid else None
    if mid and not found:
        return False                             # too old to find: whatever is featured stays
    state["featured"] = found
    send({"type": "feature", "msg": found})
    return True


SAMPLES = {
    "chat": [("twitch", "pixel_pirate", "this overlay looks great", "#ff7f50"), ("youtube", "Maya Chen", "hello from Lisbon!", ""),
             ("kick", "turbo_kat", "W stream", "#53fc18"), ("x", "Dev Daily", "one chat for every platform, nice", "")],
    # (platform, name, what they said, the platform's own sentence, alert, amount)
    "alert": [("twitch", "nightowl_42", "half a year already!", "nightowl_42 subscribed for 6 months!", "resub", "6"),
              ("youtube", "Sam Ortiz", "Keep it up!", "Super Chat $5.00", "superchat", "$5.00"),
              ("twitch", "raid_leader", "", "37 raiders from raid_leader have joined!", "raid", "37"),
              ("kick", "turbo_kat", "", "turbo_kat gifted 5 subs", "gift", "5"),
              ("twitch", "bitbucket", "Cheer500 great stream", "bitbucket cheered 500 bits", "cheer", "500 bits")],
}


async def test_event(kind):
    """Made-up events marked test, so the overlays in OBS can be checked without being live."""
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
        send({"type": "viewers", "counts": {"twitch": 128, "youtube": 342, "kick": 41, "x": 87}, "total": 598, "test": True})
        await asyncio.sleep(8)
        send(viewer_event())                     # back to the real numbers
    else:
        return False
    return True


# ---- replies and moderation, from the chat window or a paired device --------------------------------------
# Every reply and moderation goes through here. Twitch is done by the hub itself with Twitch's API once the streamer
# has connected Twitch; YouTube and X (and Twitch without that) are handed to the "executor": the chat window on this
# PC that has the CrossChat extension, which posts as the accounts signed in to that browser.
LIMIT = {"twitch": 500, "youtube": 200, "x": 140}
NAMES = {"twitch": "Twitch", "youtube": "YouTube", "x": "X", "kick": "Kick"}
MOD_ACTIONS = {"twitch": ("delete", "timeout", "ban", "unban"), "youtube": ("delete", "timeout", "ban")}
QUICK_DEFAULTS = ["Welcome in! 👋", "Thanks for the follow!", "Good question, one sec", "GG", "❤️", "Be right back, 2 minutes"]
jobs = {}                                    # job id -> future the executor's answer lands in
TW = None                                    # the Twitch API connection (set in main)
DEV = None                                   # paired devices (set in main)


def executor_event():
    return {"type": "executor", "present": state["executor"] is not None}


def twitch_event():
    return {"type": "twitch_auth", **(TW.state() if TW else {"state": "off"})}


def quick_path():
    return os.path.join(HOME, "quick.json")


def quick_replies():
    try:
        with open(quick_path(), encoding="utf-8") as f:
            found = json.load(f)
        return [str(r)[:100] for r in found][:30] if isinstance(found, list) else QUICK_DEFAULTS
    except (OSError, ValueError):
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


async def run_send(job):
    text, reply_to, to = job["text"], job.get("reply") or {}, job["to"]
    answer = {}
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


async def run_mod(job):
    p, action = job["p"], job["action"]
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
    else:
        answer = await by_executor(job) or {"ok": False, "why": NO_EXECUTOR}
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
    asyncio.create_task(run_send(job))
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
    asyncio.create_task(run_mod(job))
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
    return "http://%s:%d/" % (lan_ip(), remote_port()) if (CFG.get("remote") or {}).get("enabled", True) else None


async def remote_on():
    """Listen on the home network once there is a paired device or a pairing in progress (not before, so nothing is
    exposed and Windows doesn't ask about the firewall until the streamer pairs something)."""
    global remote_server
    if remote_server or not (CFG.get("remote") or {}).get("enabled", True) or not (DEV.devices or DEV.pairing_open()):
        return
    try:
        remote_server = await asyncio.start_server(lambda r, w: serve(r, w, remote=True), "0.0.0.0", remote_port())
        log.info("companion on %s", lan_url())
    except OSError as error:
        warn("CrossChat could not open port %d for the companion (%s). Change \"remote\": {\"port\"} in config.json."
             % (remote_port(), error.strerror))


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


REMOTE_GET = ("/", "/events", "/whoami", "/version")
REMOTE_POST = ("/send", "/mod", "/feature", "/star", "/quick", "/test")


# ---- the pages and their live feed ------------------------------------------------------------------
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".svg": "image/svg+xml", ".ico": "image/x-icon", ".png": "image/png", ".webmanifest": "application/manifest+json",
         ".json": "application/json"}
OPEN = "Access-Control-Allow-Origin: *\r\n"    # the chat itself is public: an overlay page elsewhere may read it
READ_ONLY = ("/", "/studio", "/events", "/settings", "/targets", "/version", "/themes", "/x/last")
BODY_LIMIT = 256 * 1024


def page(*path):
    with open(os.path.join(*path), "rb") as f:
        return f.read()


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


def refused(method, headers, path):
    """Why a request is turned away, or '' when it is fine.

    Only this PC's own addresses are answered (a web page can't reach the hub under another name). Anything that does
    something (open a window, start or end a livestream) is refused when another website asks for it; the OBS
    script, the Start-menu shortcuts, the extension and the hub's own pages are fine. Changes (POST) come only from
    the hub's own pages, as JSON, which a page elsewhere can't send without the browser asking first.
    """
    if headers.get("host", "") not in ("127.0.0.1:%d" % PORT, "localhost:%d" % PORT):
        return "not this address"
    origin = headers.get("origin", "")
    outsider = headers.get("sec-fetch-site") == "cross-site" or origin not in ("", "http://127.0.0.1:%d" % PORT, "http://localhost:%d" % PORT)
    readable = method == "GET" and (path in READ_ONLY or path.startswith(("/overlay/", "/web/", "/themes/", "/custom/")))
    if outsider and not readable and not (method == "GET" and origin.startswith("chrome-extension://")):
        return "not from another website"
    if method == "POST" and (outsider or headers.get("content-type", "").split(";")[0].strip() != "application/json"):
        return "not from another website"
    return ""


def remote_refused(method, headers, path, device):
    """For the companion port: why a request is turned away, or ''. Everything needs a paired device's cookie except
    pairing itself; changes must come from the companion page itself, as JSON."""
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


async def serve(reader, writer, remote=False):
    try:
        request = (await asyncio.wait_for(reader.readline(), 10)).decode("latin1").split()
        headers = {}
        while True:
            line = (await asyncio.wait_for(reader.readline(), 10)).decode("latin1")
            if line in ("\r\n", "\n", ""):
                break
            key, _, value = line.partition(":")
            headers[key.strip().lower()] = value.strip()
        if len(request) < 2 or request[0] not in ("GET", "POST"):
            return
        method = request[0]
        url = urllib.parse.urlsplit(request[1])
        query = urllib.parse.parse_qs(url.query)
        device = DEV.check(cookie_token(headers)) if remote and DEV else None
        why = remote_refused(method, headers, url.path, device) if remote else refused(method, headers, url.path)
        if remote and method == "GET" and (url.path == "/pair" or (url.path == "/" and not device)):
            token = pair_device((query.get("code") or [""])[0], headers) if query.get("code") else None
            if token:                              # the link from the QR code: paired, on to the companion
                await reply(writer, "303 See Other", "text/plain", b"", "Location: /\r\n" + device_cookie(token))
            else:
                await reply(writer, "200 OK", TYPES[".html"], PAIR_PAGE)
        elif why:
            await reply(writer, "401 Unauthorized" if why.startswith("pair") else "403 Forbidden", "text/plain", why.encode())
        elif method == "POST":
            await serve_post(reader, writer, headers, url.path, remote)
        elif url.path == "/whoami":
            body = {"remote": remote, "device": device["name"] if device else None, "version": VERSION, "lan_url": lan_url()}
            await reply(writer, "200 OK", TYPES[".json"], json.dumps(body).encode())
        elif url.path == "/":
            await reply(writer, "200 OK", TYPES[".html"], page(WEB, "window.html"))
        elif url.path == "/studio":                # the Theme Studio
            await reply(writer, "200 OK", TYPES[".html"], page(WEB, "studio.html"))
        elif url.path.startswith("/overlay/") and url.path[9:] in WIDGETS:     # what viewers see: OBS browser sources
            await reply(writer, "200 OK", TYPES[".html"], page(WEB, "overlay.html"), OPEN)
        elif re.fullmatch(r"/web/(vendor/)?[\w-]+\.(js|css|svg|ico|png|webmanifest)", url.path):
            await reply(writer, "200 OK", TYPES[os.path.splitext(url.path)[1]], page(WEB, url.path[5:]), OPEN)
        elif url.path.startswith("/custom/"):          # your own overlay pages (custom_overlays in config.json)
            found = custom_file(urllib.parse.unquote(url.path[8:]))
            if found:
                await reply(writer, "200 OK", CUSTOM_TYPES[os.path.splitext(found)[1].lower()], page(found))   # no CORS: other sites can't read them
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
            await reply(writer, "200 OK", "application/json", json.dumps({"twitch": TWITCH, "youtube_video": state["youtube_video"]}).encode())
        elif url.path == "/events":
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-store\r\n" + OPEN.encode()
                         + b"Connection: keep-alive\r\n\r\nretry: 2000\n\n")
            queue = asyncio.Queue()
            for old in list(messages):
                queue.put_nowait(old)
            for event in (status_event(), viewer_event(), {"type": "feature", "msg": state["featured"]},
                          {"type": "starred", "ids": list(starred)}, {"type": "quick", "replies": quick_replies()}, twitch_event()):
                queue.put_nowait(event)
            clients.add(queue)
            if not remote:
                local_clients.add(queue)
                queue.put_nowait(devices_event())
                if query.get("executor") == ["1"]:           # the chat window with the extension: it posts for everyone
                    state["executor"] = queue
                    send(executor_event())
            queue.put_nowait(executor_event())
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
                if state["executor"] is queue:
                    state["executor"] = None
                    send(executor_event())
        elif url.path == "/show":
            await show_window()
            await reply(writer, "200 OK", "text/plain", b"ok")
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
        elif url.path == "/x/last":
            await reply(writer, "200 OK", "application/json", json.dumps(state.get("x_last")).encode())
        else:
            await reply(writer, "404 Not Found", "text/plain", b"not found")
    except FileNotFoundError:
        await reply(writer, "404 Not Found", "text/plain", b"not found")
    except (OSError, asyncio.TimeoutError, ConnectionError):
        pass
    finally:
        try:
            writer.close()
        except OSError:
            pass


async def serve_post(reader, writer, headers, path, remote=False):
    """The Theme Studio's, the chat window's and paired devices' changes, as JSON."""
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
            write_file(quick_path(), json.dumps([" ".join(r.split()) for r in replies], ensure_ascii=False, indent=1))
            send({"type": "quick", "replies": quick_replies()})
            result = {"ok": True}
    elif path == "/outbox/result" and not remote:          # the executor's answer to a job
        future = jobs.get(str(body.get("job_id") or ""))
        if future and not future.done():
            future.set_result(body.get("answer") if isinstance(body.get("answer"), dict) else {})
        result = {"ok": bool(future)}
    elif path == "/pair/start" and not remote:
        code, expires = DEV.start_pairing()
        await remote_on()
        url = lan_url()
        result = {"ok": bool(remote_server), "code": code, "url": (url + "pair?code=" + code) if url else None, "expires": int(expires)}
        if not remote_server:
            result["why"] = "The companion is switched off in config.json (\"remote\": {\"enabled\"})."
        send({"type": "pair", **result}, only=local_clients)
    elif path == "/devices/revoke" and not remote:
        result = {"ok": DEV.revoke(str(body.get("id") or ""))}
        send(devices_event(), only=local_clients)
    elif path == "/twitch/connect" and not remote:
        if not TW.client_id:
            result = {"ok": False, "why": "This CrossChat has no Twitch app Client ID (\"twitch_client_id\" in config.json)."}
        else:
            asyncio.create_task(twitch_connect())
            result = {"ok": True}
    elif path == "/twitch/disconnect" and not remote:
        await asyncio.to_thread(TW.forget)
        send(twitch_event())
        result = {"ok": True}
    elif path in ("/themes/save", "/themes/delete", "/themes/default"):
        try:
            result = theme_change(body, path[8:])
        except OSError as error:
            result = {"ok": False, "why": "Could not write the theme file: %s" % error.strerror}
    elif path == "/test":
        result = {"ok": True}
        kind = str(body.get("kind") or "")
        if kind in ("chat", "alert", "featured", "viewers"):
            asyncio.create_task(test_event(kind))
        else:
            result = {"ok": False, "why": "unknown test"}
    else:
        await reply(writer, "404 Not Found", "text/plain", b"not found")
        return
    await reply(writer, "200 OK", TYPES[".json"], json.dumps(result).encode(), extra)


def start_log():
    path = arg("--log", os.path.join(HOME, "crosschat.log"))
    try:
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=512 * 1024, backupCount=1, encoding="utf-8")
    except OSError:
        handler = logging.NullHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    if TEST and sys.stderr:
        log.addHandler(logging.StreamHandler())
    log.setLevel(logging.INFO)


def companion_setup():
    """Paired devices and the Twitch connection, kept in your folder."""
    global DEV, TW
    DEV = Devices(os.path.join(HOME, "devices.json"))
    TW = Twitch(CFG.get("twitch_client_id") or TWITCH_CLIENT_ID, os.path.join(HOME, "twitch.bin"))


async def main():
    try:
        server = await asyncio.start_server(serve, "127.0.0.1", PORT)
    except OSError:
        log.info("port %d is taken: another CrossChat hub is already running", PORT)
        return
    companion_setup()
    await remote_on()
    log.info("CrossChat %s on http://127.0.0.1:%d (Twitch %r, YouTube %r, Kick %r, X %s)", VERSION, PORT, TWITCH, YOUTUBE, KICK,
             "on" if X else "off")
    tasks = []
    for name, wanted, job in (("twitch", TWITCH, lambda: twitch(TWITCH)), ("youtube", YOUTUBE, lambda: youtube(YOUTUBE)),
                              ("kick", KICK, lambda: kick(KICK, KICK_ROOM))):
        if wanted:
            status[name] = "off"
            tasks.append(asyncio.create_task(job()))
    if X:
        status["x"] = "off"
        tasks.append(asyncio.create_task(x_watch()))
    tasks.append(asyncio.create_task(audience()))
    async with server:
        if TEST:
            await stream_started()
            await asyncio.Event().wait()
        else:
            await obs_link()
    for t in tasks:
        t.cancel()


if __name__ == "__main__":
    configure(sys.argv[1:])
    start_log()
    asyncio.run(main())
