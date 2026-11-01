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


def tiktok_live(home):
    home({"tiktok": "sunny.daze"})
    hub.streaming.set()
    for held in (hub.tiktok_told, hub.tiktok_likes, hub.tiktok_once):
        held.clear()
    hub.status["tiktok"] = "on"


def tell(*lines):
    """What the extension passes on from the streamer's own page, straight to the hub."""
    query = {"page": "sunny.daze", "lines": json.dumps(list(lines))}
    return hub.tiktok_feed(lambda k: query.get(k, ""))


def events():
    return [(m["name"], m["alert"], m.get("amount", ""), m["system"]) for m in hub.messages if m["p"] == "tiktok" and m["kind"] == "event"]


def test_tiktok_gifts_follows_and_shares_are_alerts(home):
    tiktok_live(home)
    try:
        assert tell({"id": "g1", "kind": "gift", "name": "pixel.pal", "gift": "Rose", "count": 5},
                    {"id": "g2", "kind": "gift", "name": "star.gazer", "gift": "Galaxy", "count": 1},
                    {"id": "g3", "kind": "gift", "name": "odd.one", "gift": "", "count": "lots"},
                    {"id": "g1", "kind": "gift", "name": "pixel.pal", "gift": "Rose", "count": 5},       # the same item again
                    {"id": "f1", "kind": "follow", "name": "mira_makes"},
                    {"id": "f2", "kind": "follow", "name": "Mira_Makes"},                                # follows show once a stream
                    {"id": "s1", "kind": "share", "name": "sunny_side_up"},
                    {"id": "s2", "kind": "share", "name": "sunny_side_up"},                              # shares at most once a minute
                    {"id": "h1", "kind": "share", "name": "Sunny", "host": True},                         # the streamer's own
                    {"id": "x1", "kind": "raid", "name": "who.knows"},                                   # not a TikTok event
                    {"id": "", "kind": "gift", "name": "no.id", "gift": "Rose", "count": 1})
        assert events() == [("pixel.pal", "gift", "Rose ×5", "pixel.pal sent Rose ×5"),
                            ("star.gazer", "gift", "Galaxy", "star.gazer sent Galaxy"),
                            ("odd.one", "gift", "a gift", "odd.one sent a gift"),
                            ("mira_makes", "follow", "", "mira_makes followed"),
                            ("sunny_side_up", "share", "", "sunny_side_up shared the LIVE")]
        assert not any("$" in m.get("amount", "") for m in hub.messages)                   # no money value is made up
        tell({"id": "g9", "kind": "gift", "name": "x" * 99, "gift": "y" * 99, "count": 10 ** 9})
        last = hub.messages[-1]
        assert len(last["name"]) == 60 and last["amount"] == "y" * 40
    finally:
        hub.streaming.clear()


def test_tiktok_likes_roll_up(home, monkeypatch):
    tiktok_live(home)
    clock = [1000.0]
    monkeypatch.setattr(hub.time, "time", lambda: clock[0])
    try:
        tell({"id": "l1", "kind": "like", "name": "tap.tara", "count": 15}, {"id": "l2", "kind": "like", "name": "tap.tara", "count": 5})
        assert events() == []                                       # still liking, maybe
        clock[0] += hub.LIKE_QUIET
        tell()
        assert events() == [("tap.tara", "like", "20", "tap.tara liked the LIVE ×20")]
        for i in range(hub.LIKE_ONE_BY_ONE + 2):                    # a busy LIVE: many due at once make one line
            tell({"id": "m%d" % i, "kind": "like", "name": "fan%d" % i, "count": 2})
        clock[0] += hub.LIKE_QUIET
        tell()
        assert events()[-1] == ("%d viewers" % (hub.LIKE_ONE_BY_ONE + 2), "like", str(2 * (hub.LIKE_ONE_BY_ONE + 2)),
                                "%d viewers liked the LIVE ×%d" % (hub.LIKE_ONE_BY_ONE + 2, 2 * (hub.LIKE_ONE_BY_ONE + 2)))
        tell({"id": "l3", "kind": "like", "name": "steady.sue"})
        for _ in range(10):                                          # liking on and on: shown after LIKE_LONGEST at most
            clock[0] += hub.LIKE_LONGEST / 10
            tell({"id": "l4-%f" % clock[0], "kind": "like", "name": "steady.sue"})
        assert ("steady.sue", "like", "11", "steady.sue liked the LIVE ×11") in events()
        tell({"id": "l5", "kind": "like", "name": "last.liker"})
        hub.tiktok_off()                                             # the LIVE ends: what is left shows
        assert events()[-1][0] == "last.liker"
        hub.TTS.update(enabled=True, read="all")
        assert hub.speech(hub.messages[-1]) == ""                    # likes aren't read aloud
    finally:
        hub.TTS.update(hub.TTS_DEFAULTS)
        hub.streaming.clear()


def test_tiktok_joins_only_when_wanted(home):
    tiktok_live(home)
    saved = hub.FILTERS
    try:
        hub.FILTERS = hub.clean_filters({})
        assert hub.FILTERS["joins"] is False
        tell({"id": "j1", "kind": "join", "name": "quiet.quokka"})
        assert events() == []
        hub.FILTERS = hub.clean_filters({"joins": True})
        tell({"id": "j2", "kind": "join", "name": "quiet.quokka"}, {"id": "j3", "kind": "join", "name": "quiet.quokka"})
        assert events() == [("quiet.quokka", "join", "", "quiet.quokka joined")]     # once in a while per viewer
        assert hub.clean_filters({"joins": "yes"})["joins"] is False

        async def test(port):
            targets = json.loads((await http(port, "GET", "/targets", {"Origin": "chrome-extension://abcdefghijklmnop"}))[2])
            assert targets["tiktok_joins"] is True
        run(serving(test))
    finally:
        hub.FILTERS = saved
        hub.streaming.clear()


def test_tiktok_events_only_from_the_streamers_page(home):
    tiktok_live(home)
    try:
        query = {"page": "someone.else", "lines": json.dumps([{"id": "g1", "kind": "gift", "name": "a", "gift": "Rose", "count": 1}])}
        assert hub.tiktok_feed(lambda k: query.get(k, "")) is False
        assert events() == []
    finally:
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
