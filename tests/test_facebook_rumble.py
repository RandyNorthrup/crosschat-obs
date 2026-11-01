"""Facebook Live (comments from Live Producer, through the extension) and Rumble (its official Live Stream API)."""
import asyncio
import json
import time
import urllib.parse

import pytest

import hub
import rumble_api
from test_companion import http, post, run, serving

EXTENSION = {"Origin": "chrome-extension://abcdefghijklmnop", "Sec-Fetch-Site": "none"}


def fb_feed(port, lines=(), **more):
    query = urllib.parse.urlencode({"lines": json.dumps(list(lines)), **more})
    return http(port, "GET", "/facebook/feed?" + query, EXTENSION)


# ---- Facebook ---------------------------------------------------------------------------------------------------------
def test_facebook_comments_only_when_switched_on(home):
    home({})

    async def off(port):
        status, _, body = await fb_feed(port, [{"id": "c1", "name": "Lena", "text": "hi"}])
        assert json.loads(body) == {"mine": False} and not [m for m in hub.messages if m["p"] == "facebook"]
    run(serving(off))

    home({"facebook": True})
    assert hub.FACEBOOK and hub.LIMIT["facebook"] == 8000
    hub.facebook_told.clear()

    async def on(port):
        lines = [{"id": "Y29tbWVudDox", "name": "Lena Park", "text": "hello from Facebook"},
                 {"id": "Y29tbWVudDoy", "name": "Sunny Daze", "text": "thanks!", "host": True},
                 {"id": "Y29tbWVudDox", "name": "Lena Park", "text": "hello from Facebook"},      # seen again
                 {"id": "", "name": "No Id", "text": "still posting"}]
        assert json.loads((await fb_feed(port, lines, viewers="31"))[2]) == {"mine": True}
        shown = [(m["name"], m["text"], m["badges"]) for m in hub.messages if m["p"] == "facebook"]
        assert shown == [("Lena Park", "hello from Facebook", []), ("Sunny Daze", "thanks!", ["broadcaster"])]
        assert hub.status["facebook"] == "on" and hub.viewers["facebook"] == 31
        await fb_feed(port, over="1")
        assert hub.status["facebook"] == "off"
        assert (await http(port, "GET", "/facebook/feed", {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}))[0] == 403
    run(serving(on))


# ---- Rumble -----------------------------------------------------------------------------------------------------------
SAMPLE = {                                   # the shape of Rumble's documented example answer
    "now": 1695059500, "type": "user", "user_id": "XXXXX",
    "subscribers": {"num_subscribers": 5, "recent_subscribers": [
        {"user": "UserNameE", "username": "UserNameE", "amount_cents": 500, "amount_dollars": 5, "subscribed_on": "2030-01-01T00:00:05+00:00"},
        {"user": "Old", "username": "Old", "amount_cents": 500, "amount_dollars": 5, "subscribed_on": "2020-01-01T00:00:00+00:00"}]},
    "gifted_subs": {"num_gifted_subs": 1, "latest_gifted_sub": {"total_gifts": 1, "purchased_by": "UsernameA"}},
    "livestreams": [{"id": "7ho8uk", "title": "Title", "is_live": True, "stream_key": "SECRET-STREAM-KEY", "watching_now": 19, "chat": {
        "recent_messages": [{"username": "UserNameB", "badges": ["premium"], "text": "second", "created_on": "2030-01-01T00:00:09+00:00"},
                            {"username": "UserNameA", "badges": ["admin", "premium"], "text": "This is my chat message",
                             "created_on": "2030-01-01T00:00:08+00:00"},
                            {"username": "Earlier", "badges": [], "text": "before the stream", "created_on": "2020-01-01T00:00:00+00:00"}],
        "recent_rants": [{"username": "UserNameC", "badges": [], "text": "Rant Message", "created_on": "2030-01-01T00:00:07+00:00", "amount_cents": 500}]}}],
}


def test_rumble_reads_chat_rants_and_subs(home, monkeypatch):
    home({})
    hub.state["since"] = hub.rumble_time("2030-01-01T00:00:00+00:00")
    hub.state["local"] = True                 # (no chat window opens in a test)
    told, last = [], {}
    hub.rumble_read(SAMPLE, told, last)
    shown = [(m["kind"], m["name"], m["text"]) for m in hub.messages if m["p"] == "rumble"]
    assert ("chat", "UserNameA", "This is my chat message") in shown and ("chat", "UserNameB", "second") in shown
    assert shown.index(("chat", "UserNameA", "This is my chat message")) < shown.index(("chat", "UserNameB", "second"))   # oldest first
    assert not any(t == "before the stream" for _, _, t in shown) and not any(n == "Old" for _, n, _ in shown)
    rant = next(m for m in hub.messages if m["p"] == "rumble" and m.get("alert") == "superchat")
    assert rant["amount"] == "$5.00" and rant["text"] == "Rant Message"
    assert any(m.get("alert") == "sub" and m["name"] == "UserNameE" for m in hub.messages)
    assert hub.viewers["rumble"] == 19 and hub.status["rumble"] == "on"
    assert hub.state["rumble_chat"] == str(int("7ho8uk", 36))            # Rumble's chat pop-out number
    assert "SECRET-STREAM-KEY" not in json.dumps(list(hub.messages))      # the stream key in Rumble's answer goes nowhere
    count = len(hub.messages)
    hub.rumble_read(SAMPLE, told, last)                                   # the same answer again: nothing new
    assert len(hub.messages) == count
    more = json.loads(json.dumps(SAMPLE))
    more["gifted_subs"] = {"num_gifted_subs": 4, "latest_gifted_sub": {"total_gifts": 3, "purchased_by": "Gifter"}}
    hub.rumble_read(more, told, last)
    gift = hub.messages[-1]
    assert gift.get("alert") == "gift" and gift["name"] == "Gifter" and gift["amount"] == "3 subs"
    hub.rumble_read({"livestreams": [{"id": "7ho8uk", "is_live": False}]}, told, last)
    assert hub.status["rumble"] == "waiting" and "rumble" not in hub.viewers and hub.state["rumble_chat"] == ""


def test_rumble_url_is_checked_encrypted_and_never_shown(tmp_path, monkeypatch):
    r = rumble_api.Rumble(str(tmp_path / "rumble.bin"))
    for bad in ("https://evil.example/-livestream-api/get-data?key=abcdefgh", "http://rumble.com/-livestream-api/get-data?key=abcdefgh",
                "https://rumble.com/-livestream-api/get-data?nokey=1", "not a url"):
        with pytest.raises(rumble_api.RumbleError):
            r.set(bad)
    url = "https://rumble.com/-livestream-api/get-data?key=SECRETKEY123456"    # gitleaks:allow (made-up test value)
    r.set(url)
    assert b"SECRETKEY123456" not in (tmp_path / "rumble.bin").read_bytes()               # encrypted for this Windows user
    assert rumble_api.Rumble(str(tmp_path / "rumble.bin")).url == url

    def down(*a, **k):
        raise rumble_api.requests.ConnectionError("could not reach " + url)

    monkeypatch.setattr(rumble_api.requests, "get", down)
    with pytest.raises(rumble_api.RumbleError) as error:
        r.fetch()
    assert "SECRETKEY" not in str(error.value) and error.value.__cause__ is None           # the URL never ends up in a message

    class Refused:
        status_code, text = 403, ""

    monkeypatch.setattr(rumble_api.requests, "get", lambda *a, **k: Refused())
    with pytest.raises(rumble_api.RumbleError):
        r.fetch()
    assert "livestream-api" in r.state()["why"] and "SECRET" not in r.state()["why"]
    r.forget()
    assert not (tmp_path / "rumble.bin").exists() and not r.on()


def test_rumble_connect_is_this_pc_only(home):
    home({})

    async def test(port):
        answer = json.loads((await post(port, "/rumble/connect", {"url": "https://rumble.com/-livestream-api/get-data?key=ABCDEFGH12"}))[2])
        assert answer == {"ok": True} and hub.RB.on()
        assert json.loads((await post(port, "/rumble/connect", {"url": "https://evil.example/x?key=1"}))[2])["ok"] is False
        targets = json.loads((await http(port, "GET", "/targets", EXTENSION))[2])
        assert "ABCDEFGH" not in json.dumps(targets)                       # the URL is never handed out
        assert json.loads((await post(port, "/rumble/disconnect", {}))[2]) == {"ok": True} and not hub.RB.on()
    run(serving(test))

    async def remote(port):
        code, _ = hub.DEV.start_pairing()
        _, head, _ = await http(port, "GET", "/pair?code=" + code)
        cookie = {"Cookie": "cc_device=" + head.split("cc_device=")[1].split(";")[0]}
        origin = {"Origin": "http://127.0.0.1:%d" % port, "Content-Type": "application/json", **cookie}
        assert (await post(port, "/rumble/connect", {"url": "https://rumble.com/-livestream-api/get-data?key=ABCDEFGH12"}, origin))[0] == 403
    run(serving(remote, remote=True))


def test_rumble_replies_go_through_the_extension(home):
    home({})

    async def test(port):
        executor = asyncio.Queue()
        hub.clients.add(executor)
        hub.state["executor"] = executor
        assert json.loads((await post(port, "/send", {"to": ["rumble"], "text": "x" * 201}))[2])["ok"] is False
        answer = json.loads((await post(port, "/send", {"to": ["rumble"], "text": "thanks Rumble!"}))[2])
        await asyncio.sleep(0.05)
        job = next(e["job"] for e in (executor.get_nowait() for _ in range(executor.qsize())) if e["type"] == "outbox")
        assert job["to"] == ["rumble"] and job["id"] == answer["job_id"]
        hub.jobs[job["id"]].set_result({"rumble": {"ok": True}})
    run(serving(test))
    assert time.time()
