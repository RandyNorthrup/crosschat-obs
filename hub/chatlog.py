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


def cell(value):
    """A chat line as a spreadsheet cell. Viewers write the chat, and a line starting with = + - @ (or a tab or
    return) would be run as a formula when the CSV is opened in Excel; a leading ' keeps it plain text."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


class ChatLog:
    def __init__(self, folder, keep_days=90):
        self.folder, self.keep_days = folder, keep_days
        self.file, self.name, self.count = None, None, 0

    # ---- writing ----------------------------------------------------------------------------------------
    def start(self, now=None):
        """A new file for a stream that just started."""
        self.stop()
        os.makedirs(self.folder, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d_%H%M", time.localtime(now or time.time()))
        name, n = stamp, 1
        while os.path.exists(self.path(name)):
            n += 1
            name = "%s-%d" % (stamp, n)
        self.name, self.count = name, 0
        self.file = open(self.path(name), "a", encoding="utf-8")
        self.prune()
        return name

    def write(self, event):
        if not self.file:
            return
        self.file.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.file.flush()
        if event.get("type") == "msg":
            self.count += 1

    def stop(self):
        if self.file:
            self.file.close()
        self.file = None

    def prune(self):
        cutoff = time.time() - self.keep_days * 86400
        for name in os.listdir(self.folder):
            full = os.path.join(self.folder, name)
            if name.endswith(".jsonl") and os.path.getmtime(full) < cutoff:
                try:
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
            with open(full, encoding="utf-8") as f:
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
        with open(self.path(name), encoding="utf-8") as f:
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
        colours = {"twitch": "#9146ff", "youtube": "#ff0033", "kick": "#2fb60a", "x": "#555", "system": "#888"}
        lines = []
        for m in rows:
            when = time.strftime("%H:%M:%S", time.localtime((m.get("t") or 0) / 1000))
            text = ((m.get("system") or "") + " " + (m.get("text") or "")).strip() if m.get("kind") == "event" else m.get("text", "")
            lines.append('<tr class="%s"><td>%s</td><td style="color:%s">%s</td><td><b>%s</b></td><td>%s</td></tr>' % (
                ("gone" if m.get("gone") else "") + (" event" if m.get("kind") == "event" else "") + (" q" if m.get("question") else ""),
                when, colours.get(m.get("p"), "#888"), html.escape(m.get("p", "")), html.escape(m.get("name", "")), html.escape(text)))
        page = ("<!doctype html><meta charset=utf-8><title>CrossChat chat %s</title><style>body{font:14px 'Segoe UI',sans-serif;margin:24px;"
                "color:#1d2733}table{border-collapse:collapse;width:100%%}td{padding:4px 8px;border-bottom:1px solid #e1d6c6;vertical-align:top}"
                "td:first-child{color:#888;white-space:nowrap;font-family:Consolas,monospace}.gone td{text-decoration:line-through;opacity:.5}"
                ".event td{background:#fbf3ea}.q td:last-child::after{content:' ?';color:#a35d33;font-weight:bold}</style>"
                "<h1>Chat, %s</h1><p>%d messages. Made by CrossChat.</p><table>%s</table>") % (
            html.escape(name), html.escape(name.replace("_", " ")), len(rows), "".join(lines))
        return page.encode("utf-8")
