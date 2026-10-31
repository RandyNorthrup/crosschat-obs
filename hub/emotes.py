"""Third-party emotes for the chat: 7TV, BetterTTV and FrankerFaceZ.

Twitch's own emotes come with each message. These three services add more, by name: a chat line containing the
word "KEKW" shows that emote's picture. Each service has a global set and one per Twitch channel; all three are
public and need no account. The result is one map from emote name to picture URL, sent to every page.
"""
import re

import requests

TIMEOUT = 10
# What the pages will show: a plain word as the name, and a picture on the service's own https site. Anything else
# (a channel's emote set is written by whoever runs that channel) is left out.
EMOTE_NAME = re.compile(r"[^\s<>\"'`]{1,100}")
PICTURE = re.compile(r"https://(cdn\.betterttv\.net|cdn\.frankerfacez\.com|cdn\.7tv\.app)/[\w./-]+")


def _get(url):
    r = requests.get(url, timeout=TIMEOUT)
    if r.status_code == 404:                 # the channel has no set on that service
        return None
    r.raise_for_status()
    return r.json()


def bttv(data):
    """BetterTTV: a list of emotes (global), or {channelEmotes, sharedEmotes} (a channel)."""
    found = data if isinstance(data, list) else (data or {}).get("channelEmotes", []) + (data or {}).get("sharedEmotes", [])
    return {e["code"]: "https://cdn.betterttv.net/emote/%s/2x.webp" % e["id"] for e in found if e.get("code") and e.get("id")}


def ffz(data):
    """FrankerFaceZ: {sets: {id: {emoticons: [{name, urls: {"1", "2", "4"}}]}}}."""
    out = {}
    for room_set in ((data or {}).get("sets") or {}).values():
        for e in room_set.get("emoticons") or []:
            urls = e.get("urls") or {}
            url = urls.get("2") or urls.get("1")
            if e.get("name") and url:
                out[e["name"]] = url if url.startswith("http") else "https:" + url
    return out


def seventv(data):
    """7TV: an emote set {emotes: [...]}, or a user {emote_set: {emotes: [...]}}."""
    emote_set = (data or {}).get("emote_set") or data or {}
    out = {}
    for e in emote_set.get("emotes") or []:
        host = ((e.get("data") or {}).get("host") or {}).get("url")
        if e.get("name") and host:
            out[e["name"]] = ("https:" + host if host.startswith("//") else host) + "/2x.webp"
    return out


SOURCES = {
    "bttv": (bttv, "https://api.betterttv.net/3/cached/emotes/global", "https://api.betterttv.net/3/cached/users/twitch/%s"),
    "ffz": (ffz, "https://api.frankerfacez.com/v1/set/global", "https://api.frankerfacez.com/v1/room/id/%s"),
    "7tv": (seventv, "https://7tv.io/v3/emote-sets/global", "https://7tv.io/v3/users/twitch/%s"),
}


def load(twitch_id="", which=("bttv", "ffz", "7tv")):
    """All emotes of the chosen services, global and (with a Twitch channel id) the channel's. A service that fails
    is left out rather than failing the rest. Later services win a name clash; the channel's own sets win last."""
    out, problems = {}, []
    twitch_id = re.sub(r"\D", "", str(twitch_id or ""))
    for kind in which:
        parse, global_url, channel_url = SOURCES[kind]
        urls = [global_url] + ([channel_url % twitch_id] if twitch_id else [])
        for url in urls:
            try:
                out.update(safe(parse(_get(url))))
            except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as error:
                problems.append("%s: %s" % (kind, error))
    return out, problems


def safe(found):
    return {name: url for name, url in found.items()
            if isinstance(name, str) and isinstance(url, str) and EMOTE_NAME.fullmatch(name) and PICTURE.fullmatch(url)}
