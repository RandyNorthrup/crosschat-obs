"""Chat history: every stream's chat kept on this PC, one file per stream, to search and export afterwards.

Each stream gets logs/<YYYY-MM-DD_HHMM>.jsonl in your CrossChat folder: one JSON object per line (the chat messages
and events exactly as the pages get them, then deletions as {"type": "delete"/"purge", ...}). Old files are removed
after "keep_days". Exports (CSV, HTML) are built from a file when asked for.
"""
import csv
import html
import io
import json
import os
import re
import time

NAME = re.compile(r"\d{4}-\d{2}-\d{2}_\d{4}(-\d+)?")
COLOURS = {"twitch": "#9146ff", "youtube": "#ff0033", "kick": "#2fb60a", "x": "#555", "tiktok": "#c8103a", "facebook": "#1668d8",
           "instagram": "#c4005a", "rumble": "#3f7d1a", "system": "#888"}      # (dark enough to read on the export's white page)


def cell(value):
    """A chat line as a spreadsheet cell. Viewers write the chat, and a line starting with = + - @ (or a tab or
    return) would be run as a formula when the CSV is opened in Excel; a leading ' keeps it plain text."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


class ChatLog:
    def __init__(self, folder, keep_days=90, failed=None):
        """failed: told, in words for the streamer, when this stream's history has to stop."""
        self.folder, self.keep_days, self.failed = folder, keep_days, failed
        self.file, self.name = None, None

    # ---- writing ----------------------------------------------------------------------------------------
    def start(self, now=None):
        """A new file for a stream that just started: its name, or None when it can't be written (chat goes on without it)."""
        self.stop()
        try:
            os.makedirs(self.folder, exist_ok=True)
            stamp = time.strftime("%Y-%m-%d_%H%M", time.localtime(now or time.time()))
            name, n = stamp, 1
            while os.path.exists(self.path(name)):
                n += 1
                name = "%s-%d" % (stamp, n)
            self.file = open(self.path(name), "a", encoding="utf-8", errors="replace")
        except OSError as error:
            self.give_up(error)
            return None
        self.name = name
        self.prune()
        return name

    def write(self, event):
        if not self.file:
            return
        try:
            self.file.write(json.dumps(event, ensure_ascii=False) + "\n")
            self.file.flush()
        except OSError as error:
            self.give_up(error)

    def give_up(self, error):
        """History can't be written (a full disk, say), and that must never get in the way of chat: this stream's file
        stays where it got to, and the streamer is told."""
        self.stop()
        if self.failed:
            self.failed("CrossChat can't write this stream's chat history (%s), so it stops here. Chat itself carries on." % (
                error.strerror or error))

    def stop(self):
        file, self.file = self.file, None
        if file:
            try:
                file.close()
            except OSError:                      # (what was still waiting to be written; give_up has said so)
                pass

    def prune(self):
        cutoff = time.time() - self.keep_days * 86400
        try:
            names = os.listdir(self.folder)
        except OSError:
            return
        for name in names:
            full = os.path.join(self.folder, name)
            try:
                if name.endswith(".jsonl") and os.path.getmtime(full) < cutoff:
                    os.remove(full)
            except OSError:
                pass

    # ---- reading ----------------------------------------------------------------------------------------
    def path(self, name):
        return os.path.join(self.folder, name + ".jsonl")

    def listing(self):
        out = []
        try:
            names = [f[:-6] for f in os.listdir(self.folder) if f.endswith(".jsonl") and NAME.fullmatch(f[:-6])]
        except OSError:
            names = []
        for name in names:
            full = self.path(name)
            first = last = None
            messages = 0
            with open(full, encoding="utf-8", errors="replace") as f:     # (a full disk can leave half a character at the end)
                for line in f:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if e.get("type") == "msg":
                        messages += 1
                        first = first or e.get("t")
                        last = e.get("t")
            started = first or int(os.path.getctime(full) * 1000)
            out.append({"name": name, "started": started, "ended": None if name == self.name and self.file else last,
                        "messages": messages, "bytes": os.path.getsize(full)})
        return sorted(out, key=lambda x: x["name"], reverse=True)

    def messages(self, name):
        """The stream's messages in order, with deleted ones marked {"gone": true}."""
        if not NAME.fullmatch(name or "") or not os.path.isfile(self.path(name)):
            return None
        rows, gone, purged = [], set(), set()
        with open(self.path(name), encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("type") == "msg":
                    rows.append(e)
                elif e.get("type") == "delete":
                    gone.add(e.get("id"))
                elif e.get("type") == "purge":
                    purged.add((e.get("p"), str(e.get("name", "")).lower()))
        for m in rows:
            if m.get("id") in gone or (m.get("p"), str(m.get("name", "")).lower()) in purged:
                m["gone"] = True
        return rows

    def csv(self, name):
        rows = self.messages(name)
        if rows is None:
            return None
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["time", "platform", "name", "message", "kind", "alert", "amount", "question", "deleted"])
        for m in rows:
            when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime((m.get("t") or 0) / 1000))
            text = ((m.get("system") or "") + " " + (m.get("text") or "")).strip() if m.get("kind") == "event" else m.get("text", "")
            w.writerow([when, m.get("p", ""), cell(m.get("name", "")), cell(text), m.get("kind", ""), cell(m.get("alert", "")),
                        cell(m.get("amount", "")), "yes" if m.get("question") else "", "yes" if m.get("gone") else ""])
        return ("﻿" + out.getvalue()).encode("utf-8")       # the mark makes Excel read it as UTF-8

    def html(self, name):
        rows = self.messages(name)
        if rows is None:
            return None
        lines = []
        for m in rows:
            when = time.strftime("%H:%M:%S", time.localtime((m.get("t") or 0) / 1000))
            text = ((m.get("system") or "") + " " + (m.get("text") or "")).strip() if m.get("kind") == "event" else m.get("text", "")
            lines.append('<tr class="%s"><td>%s</td><td style="color:%s">%s</td><td><b>%s</b></td><td>%s</td></tr>' % (
                ("gone" if m.get("gone") else "") + (" event" if m.get("kind") == "event" else "") + (" q" if m.get("question") else ""),
                when, COLOURS.get(m.get("p"), "#888"), html.escape(m.get("p", "")), html.escape(m.get("name", "")), html.escape(text)))
        page = ("<!doctype html><meta charset=utf-8><title>CrossChat chat %s</title><style>body{font:14px 'Segoe UI',sans-serif;margin:24px;"
                "color:#1d2733}table{border-collapse:collapse;width:100%%}td{padding:4px 8px;border-bottom:1px solid #e1d6c6;vertical-align:top}"
                "td:first-child{color:#888;white-space:nowrap;font-family:Consolas,monospace}.gone td{text-decoration:line-through;opacity:.5}"
                ".event td{background:#fbf3ea}.q td:last-child::after{content:' ?';color:#a35d33;font-weight:bold}</style>"
                "<h1>Chat, %s</h1><p>%d messages. Made by CrossChat.</p><table>%s</table>") % (
            html.escape(name), html.escape(name.replace("_", " ")), len(rows), "".join(lines))
        return page.encode("utf-8")
