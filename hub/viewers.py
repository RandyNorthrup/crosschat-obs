"""Viewer cards: one viewer's messages this stream and in earlier streams' chat history, for the CrossChat window and
paired devices.

lookup() reads this stream's history file (or, with history off, the messages the hub still holds) and then the older
files newest first. Only lines that mention the viewer are decoded, and the reading stops at fixed limits, so a big
history folder can't keep the hub busy or send a phone megabytes of chat.
"""
import json
import os
import re

from chatlog import NAME

STREAM_LIMIT = 200                           # messages shown from this stream
PAST_LIMIT = 200                             # ... and from earlier streams
PAST_FILES = 60                              # earlier streams looked through
PAST_BYTES = 32 * 1024 * 1024                # history read for earlier streams, at most
CURRENT_BYTES = 64 * 1024 * 1024             # ... and for this one
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
UID = re.compile(r"[\w.:@|-]{1,128}")
KEEP = ("id", "t", "p", "name", "text", "color", "badges", "kind", "emotes", "handle", "uid", "alert", "amount", "system",
        "mid", "first", "question", "hidden", "gone")


class ViewerError(ValueError):
    pass


def checked(platform, name, uid, q, platforms):
    """The request's parts, or ViewerError saying what is wrong."""
    if platform not in platforms:
        raise ViewerError("Unknown platform.")
    name = (name or "").strip()
    if not 1 <= len(name) <= 100 or CONTROL.search(name):
        raise ViewerError("A viewer's name is 1 to 100 characters.")
    uid = (uid or "").strip()
    if uid and not UID.fullmatch(uid):
        raise ViewerError("That isn't a viewer id.")
    q = (q or "").strip()
    if len(q) > 100 or CONTROL.search(q):
        raise ViewerError("Search for up to 100 characters.")
    return name, uid, q.casefold()


class Match:
    """Whether a chat line is this viewer's: the platform's id when both have one (two people can share a YouTube
    name), else the name or @handle, ignoring case."""
    def __init__(self, platform, name, uid):
        self.platform, self.name, self.uid = platform, name.casefold(), uid
        # the name as it is written inside a history file's JSON, to skip other people's lines without decoding them
        self.needles = [json.dumps(name, ensure_ascii=False)[1:-1].casefold()]
        if uid:
            self.needles.append(json.dumps(uid)[1:-1].casefold())

    def maybe(self, line):
        folded = line.casefold()
        return any(n in folded for n in self.needles)

    def __call__(self, m):
        if m.get("type", "msg") != "msg" or m.get("p") != self.platform or m.get("kind") == "note":
            return False
        if self.uid and m.get("uid"):
            return m["uid"] == self.uid
        return self.name in (str(m.get("name", "")).casefold(), str(m.get("handle", "")).casefold())


def shown(m, stream=None):
    out = {k: m[k] for k in KEEP if m.get(k) not in (None, "", [], False)}
    if stream:
        out["stream"] = stream
    return out


def read(path, match, budget):
    """(this viewer's messages in the file, oldest first, with deleted ones marked; bytes read; whether the budget ran
    out first)."""
    rows, gone, purged, used = [], set(), set(), 0
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                used += len(line)
                if used > budget:
                    return mark(rows, gone, purged), used, True
                if '"delete"' in line:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if e.get("type") == "delete":
                        gone.add(e.get("id"))
                        continue
                if not match.maybe(line):
                    continue
                try:
                    e = json.loads(line)
                except ValueError:                   # a line still being written, or a damaged one
                    continue
                if not isinstance(e, dict):
                    continue
                if e.get("type") == "purge" and e.get("p") == match.platform:
                    purged.add(str(e.get("name", "")).casefold())
                elif match(e):
                    rows.append(e)
    except OSError:
        pass
    return mark(rows, gone, purged), used, False


def mark(rows, gone, purged):
    for m in rows:
        if m.get("id") in gone or str(m.get("name", "")).casefold() in purged:
            m["gone"] = True
    return rows


def lookup(platform, name, uid="", q="", recent=(), folder=None, current=None, platforms=()):
    """One viewer's card. recent: the messages the hub holds (a copy); folder: the chat history folder, or None;
    current: this stream's history file name when history is on."""
    name, uid, q = checked(platform, name, uid, q, platforms)
    match = Match(platform, name, uid)
    if current and folder and NAME.fullmatch(current):
        mine, _, cut = read(os.path.join(folder, current + ".jsonl"), match, CURRENT_BYTES)
    else:
        mine, cut = [m for m in recent if match(m)], False
    chat = [m for m in mine if m.get("kind") == "chat"]
    latest = (chat or mine or [{}])[-1]
    card = {"ok": True, "p": platform, "name": latest.get("name") or name, "handle": latest.get("handle", ""),
            "uid": latest.get("uid") or uid, "color": latest.get("color", ""), "badges": latest.get("badges", []),
            "count": len(chat), "first_seen": chat[0].get("t") if chat else None,
            "first_ever": any(m.get("first") == "ever" for m in chat), "history": bool(folder and current)}
    found = [m for m in reversed(mine) if not q or q in str(m.get("text", "")).casefold()]
    card["stream"] = [shown(m) for m in found[:STREAM_LIMIT]]
    card["truncated"] = cut or len(found) > STREAM_LIMIT
    past, streams, used = [], 0, 0
    try:
        files = sorted((f[:-6] for f in os.listdir(folder) if f.endswith(".jsonl") and NAME.fullmatch(f[:-6]) and f[:-6] != current),
                       reverse=True) if folder else []
    except OSError:
        files = []
    for n, stream in enumerate(files):
        if n >= PAST_FILES or used >= PAST_BYTES or len(past) >= PAST_LIMIT:
            card["truncated"] = True
            break
        rows, size, cut = read(os.path.join(folder, stream + ".jsonl"), match, PAST_BYTES - used)
        used += size
        if any(m.get("kind") == "chat" for m in rows):
            streams += 1
        past.extend(shown(m, stream) for m in reversed(rows) if not q or q in str(m.get("text", "")).casefold())
        card["truncated"] = card["truncated"] or cut
    card["past"] = past[:PAST_LIMIT]
    card["past_streams"] = streams
    card["truncated"] = card["truncated"] or len(past) > PAST_LIMIT
    return card
