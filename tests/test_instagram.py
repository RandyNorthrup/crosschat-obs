"""Instagram Live (comments from its Live producer on instagram.com, through the extension)."""
import json
import time
import urllib.parse

import hub
from test_companion import http, run, serving

EXTENSION = {"Origin": "chrome-extension://abcdefghijklmnop", "Sec-Fetch-Site": "none"}


def ig_feed(port, lines=(), **more):
    query = urllib.parse.urlencode({"lines": json.dumps(list(lines)), **more})
    return http(port, "GET", "/instagram/feed?" + query, EXTENSION)


def test_instagram_setting(home):
    home({})
    assert hub.INSTAGRAM is False and "instagram" not in hub.status
    for value in (True, "on", "yes", "1"):
        home({"instagram": value})
        assert hub.INSTAGRAM is True
    home({"instagram": "maybe"})
    assert hub.INSTAGRAM is False
    assert hub.NAMES["instagram"] == "Instagram" and hub.LIMIT["instagram"] == 2200


def test_instagram_comments_only_when_switched_on(home):
    home({})

    async def off(port):
        status, _, body = await ig_feed(port, [{"id": "abc1n1", "name": "lena.park", "text": "hi"}])
        assert json.loads(body) == {"mine": False} and not [m for m in hub.messages if m["p"] == "instagram"]
        assert json.loads((await http(port, "GET", "/targets", EXTENSION))[2])["instagram"] is False
    run(serving(off))

    home({"instagram": True})
    hub.instagram_told.clear()

    async def on(port):
        assert json.loads((await http(port, "GET", "/targets", EXTENSION))[2])["instagram"] is True
        lines = [{"id": "1x2y3n1", "name": "lena.park", "text": "hello from Instagram"},
                 {"id": "9z8wn1", "name": "sunny.daze", "text": "thanks!", "host": True},
                 {"id": "1x2y3n1", "name": "lena.park", "text": "hello from Instagram"},      # drawn again: the same id
                 {"id": "1x2y3n2", "name": "lena.park", "text": "hello from Instagram"},      # said twice: a new one
                 {"id": "", "name": "no.id", "text": "skipped"},
                 {"id": "q1n1", "name": "  ", "text": "no name"},
                 "not a comment"]
        assert json.loads((await ig_feed(port, lines, viewers="1200"))[2]) == {"mine": True}
        shown = [(m["name"], m["text"], m["badges"], m["id"]) for m in hub.messages if m["p"] == "instagram"]
        assert shown == [("lena.park", "hello from Instagram", [], "ig-1x2y3n1"), ("sunny.daze", "thanks!", ["broadcaster"], "ig-9z8wn1"),
                         ("lena.park", "hello from Instagram", [], "ig-1x2y3n2")]
        assert hub.status["instagram"] == "on" and hub.viewers["instagram"] == 1200
        await ig_feed(port, over="1")
        assert hub.status["instagram"] == "off" and "instagram" not in hub.viewers
        assert (await http(port, "GET", "/instagram/feed", {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}))[0] == 403
    run(serving(on))


def test_instagram_comments_are_capped(home):
    home({"instagram": True})
    hub.instagram_told.clear()
    first = lambda k: {"lines": json.dumps([{"id": "a" * 300 + "<>\"'", "name": "n" * 200, "text": "t" * 5000}] * 80)}.get(k, "")   # noqa: E731
    assert hub.instagram_feed(first) is True
    shown = [m for m in hub.messages if m["p"] == "instagram"]
    assert len(shown) == 1                                       # one id, however many times it comes
    assert shown[0]["id"] == "ig-" + "a" * 80 and len(shown[0]["name"]) == 60 and len(shown[0]["text"]) == 1000


def test_instagram_goes_quiet_when_the_producer_stops_reporting(home):
    home({"instagram": True})
    hub.status["instagram"] = "on"
    hub.viewers["instagram"] = 5
    hub.state["instagram_seen"] = time.time() - 60

    async def watch():
        task = hub.asyncio.create_task(hub.x_watch())
        await hub.asyncio.sleep(5.5)
        task.cancel()
    run(watch())
    assert hub.status["instagram"] == "off" and "instagram" not in hub.viewers


def test_instagram_page_has_a_place_on_screen(home, monkeypatch):
    home({"instagram": True})
    monkeypatch.setattr(hub, "work_area", lambda: (0, 0, 1920, 1040))
    chat = hub.box("auto", "chat")
    page = hub.box("auto", "instagram")
    assert page[0] == chat[0] and page[1] >= chat[1] + chat[3]
    assert hub.box({"x": 1, "y": 2, "width": 300, "height": 400}, "instagram") == (1, 2, 300, 400)
