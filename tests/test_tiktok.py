"""TikTok LIVE: chat from the streamer's own LIVE page, passed on by the extension; nothing from anyone else's."""
import asyncio
import json
import urllib.parse

import hub
from test_companion import http, post, run, serving


def feed(port, page, lines=(), **more):
    query = urllib.parse.urlencode({"page": page, "lines": json.dumps(list(lines)), **more})
    return http(port, "GET", "/tiktok/feed?" + query, {"Origin": "chrome-extension://abcdefghijklmnop", "Sec-Fetch-Site": "none"})


def test_tiktok_names_are_cleaned():
    assert hub.channel("@Sunny.Daze", "tiktok") == "sunny.daze"
    assert hub.channel("https://www.tiktok.com/@sunny.daze/live?lang=en", "tiktok") == "sunny.daze"
    assert hub.channel("not a name!", "tiktok") == ""
    assert hub.channel("a", "tiktok") == ""


def test_only_the_streamers_own_page_counts(home):
    home({"tiktok": "@sunny.daze"})
    assert hub.TIKTOK == "sunny.daze" and hub.LIMIT["tiktok"] == 150
    hub.streaming.set()
    hub.tiktok_told.clear()

    async def test(port):
        status, _, body = await feed(port, "someone.else", [{"id": "a1", "name": "Stranger", "text": "hello"}])
        assert status == 200 and json.loads(body) == {"mine": False}
        assert not [m for m in hub.messages if m["p"] == "tiktok"]          # another LIVE's chat is never shown
        lines = [{"id": "b1", "name": "lofi.leo", "text": "hi from TikTok"},
                 {"id": "b2", "name": "Sunny", "text": "thanks for coming", "host": True},
                 {"id": "b1", "name": "lofi.leo", "text": "hi from TikTok"},       # the same line again (after a reload)
                 {"id": "b3", "name": "", "text": "no name"}, "not a line"]
        status, _, body = await feed(port, "Sunny.Daze", lines, viewers="214")
        assert json.loads(body) == {"mine": True}
        shown = [(m["name"], m["text"], m["badges"]) for m in hub.messages if m["p"] == "tiktok"]
        assert shown == [("lofi.leo", "hi from TikTok", []), ("Sunny", "thanks for coming", ["broadcaster"])]
        assert hub.status["tiktok"] == "on" and hub.viewers["tiktok"] == 214
        await feed(port, "sunny.daze", over="1")
        assert hub.status["tiktok"] == "off" and "tiktok" not in hub.viewers
        # only the extension (or a program on this PC) may report; websites may not
        assert (await http(port, "GET", "/tiktok/feed?page=sunny.daze", {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}))[0] == 403
        targets = json.loads((await http(port, "GET", "/targets", {"Origin": "chrome-extension://abcdefghijklmnop"}))[2])
        assert targets["tiktok"] == "sunny.daze" and targets["live"] is True
    run(serving(test))
    hub.streaming.clear()


def test_tiktok_replies_go_through_the_extension(home):
    home({"tiktok": "sunny.daze"})

    async def test(port):
        executor = asyncio.Queue()
        hub.clients.add(executor)
        hub.state["executor"] = executor
        answer = json.loads((await post(port, "/send", {"to": ["tiktok"], "text": "x" * 151}))[2])
        assert answer["ok"] is False and "TikTok" in answer["why"]
        answer = json.loads((await post(port, "/send", {"to": ["tiktok"], "text": "thanks!"}))[2])
        await asyncio.sleep(0.05)
        job = next(e["job"] for e in (executor.get_nowait() for _ in range(executor.qsize())) if e["type"] == "outbox")
        assert job["to"] == ["tiktok"] and job["text"] == "thanks!" and job["id"] == answer["job_id"]
        hub.jobs[job["id"]].set_result({"tiktok": {"ok": True}})
    run(serving(test))
