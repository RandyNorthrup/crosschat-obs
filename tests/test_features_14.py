"""1.4: third-party emotes, chat history, filters, first-time chatters, connection health, reading chat aloud,
Kick replies and moderation, and the safety rules around them."""
import asyncio
import json
import os
import time
import urllib.parse

import pytest
import requests

import emotes
import hub
import kick_api
import twitch_api
from chatlog import ChatLog
from test_companion import http, post, run, same_origin, serving


def events_in(payload):
    return [json.loads(line[6:]) for line in payload.decode().splitlines() if line.startswith("data: ")]


@pytest.fixture
def fresh(home):
    def setup(config=None):
        folder = home(config)
        hub.seen.clear()
        hub.health.clear()
        hub.EMOTES.clear()
        hub.state["speaker"] = None
        return folder
    return setup


# ---- emotes ---------------------------------------------------------------------------------------------------
def test_emote_lists_from_each_service():
    assert emotes.bttv([{"id": "a1", "code": "catJAM"}]) == {"catJAM": "https://cdn.betterttv.net/emote/a1/2x.webp"}
    assert emotes.bttv({"channelEmotes": [{"id": "c", "code": "Mine"}], "sharedEmotes": [{"id": "s", "code": "Shared"}]}).keys() == {"Mine", "Shared"}
    assert emotes.ffz({"sets": {"3": {"emoticons": [{"name": "LilZ", "urls": {"1": "//cdn.frankerfacez.com/emote/1/1",
                                                                                 "2": "https://cdn.frankerfacez.com/emote/1/2"}}]}}}) == {
        "LilZ": "https://cdn.frankerfacez.com/emote/1/2"}
    seven = {"emote_set": {"emotes": [{"name": "EZ", "data": {"host": {"url": "//cdn.7tv.app/emote/01ABC"}}}]}}
    assert emotes.seventv(seven) == {"EZ": "https://cdn.7tv.app/emote/01ABC/2x.webp"}


def test_emotes_that_could_harm_a_page_are_left_out():
    kept = emotes.safe({"Fine": "https://cdn.7tv.app/emote/1/2x.webp",
                        "M&Mjc": "https://cdn.betterttv.net/emote/2/2x.webp",
                        "<img src=x onerror=alert(1)>": "https://cdn.7tv.app/emote/3/2x.webp",
                        'say"hi': "https://cdn.7tv.app/emote/4/2x.webp",
                        "Elsewhere": "https://evil.example/emote.webp",
                        "Plain": "http://cdn.7tv.app/emote/5/2x.webp",
                        "Script": "javascript:alert(1)//cdn.7tv.app/",
                        "Sneaky": "https://cdn.7tv.app/emote/6\"onload=\"x"})
    assert kept == {"Fine": "https://cdn.7tv.app/emote/1/2x.webp", "M&Mjc": "https://cdn.betterttv.net/emote/2/2x.webp"}


def test_emote_loading_survives_a_failing_service(monkeypatch):
    asked = []

    def fake(url):
        asked.append(url)
        if "frankerfacez" in url:
            raise requests.ConnectionError("down")
        return [{"id": "x", "code": "Kept"}] if "betterttv" in url else None

    monkeypatch.setattr(emotes, "_get", fake)
    found, problems = emotes.load("12ab/../3", ("bttv", "ffz"))
    assert found == {"Kept": "https://cdn.betterttv.net/emote/x/2x.webp"}
    assert problems and all(p.startswith("ffz") for p in problems)
    assert "https://api.betterttv.net/3/cached/users/twitch/123" in asked       # only the digits of the channel id are used


# ---- chat history ----------------------------------------------------------------------------------------------
def message(text, name="viewer", p="twitch", mid=None, **more):
    return {"type": "msg", "id": mid or "m-" + text, "t": int(time.time() * 1000), "p": p, "name": name, "text": text, "kind": "chat", **more}


def test_chat_history_marks_deleted_messages(tmp_path):
    log = ChatLog(str(tmp_path / "logs"))
    name = log.start()
    log.write(message("hello", mid="a"))
    log.write(message("rude", mid="b"))
    log.write(message("spam", name="Spammer", mid="c"))
    log.write({"type": "delete", "id": "b"})
    log.write({"type": "purge", "p": "twitch", "name": "spammer"})
    log.stop()
    rows = log.messages(name)
    assert [(m["text"], bool(m.get("gone"))) for m in rows] == [("hello", False), ("rude", True), ("spam", True)]
    assert log.listing()[0]["messages"] == 3
    assert log.messages("..\\..\\config") is None and log.messages("2026-01-01_0000") is None


def test_chat_history_exports_are_safe_to_open(tmp_path):
    log = ChatLog(str(tmp_path / "logs"))
    name = log.start()
    log.write(message('=HYPERLINK("http://evil.example","click")', name="@attacker"))
    log.write(message("+1 nice", name="-dash"))
    log.write(message("<script>alert(1)</script>", name="<b>bold</b>"))
    log.stop()
    text = log.csv(name).decode("utf-8-sig")
    assert "'=HYPERLINK" in text and "'@attacker" in text and "'+1 nice" in text and "'-dash" in text
    page = log.html(name).decode()
    assert "<script>" not in page and "&lt;script&gt;" in page and "<b>bold</b>" not in page


def test_old_chat_history_is_removed(tmp_path):
    folder = tmp_path / "logs"
    folder.mkdir()
    old = folder / "2020-01-01_1200.jsonl"
    old.write_text("{}\n")
    os.utime(old, (time.time() - 100 * 86400,) * 2)
    ChatLog(str(folder), keep_days=90).start()
    assert not old.exists()


# ---- filters, first-time chatters, health ---------------------------------------------------------------------------
def test_filters_hide_without_deleting(fresh):
    fresh()
    hub.FILTERS = hub.clean_filters({"words": ["spoiler", "  bad   word "], "users": ["@Troll"], "hide_commands": True})
    assert hub.FILTERS["words"] == ["spoiler", "bad word"]
    assert hub.hidden_reason("Nightbot", "Follow the stream!") == "bot"
    assert hub.hidden_reason("troll", "hi") == "user"
    assert hub.hidden_reason("viewer", "!discord") == "command"
    assert hub.hidden_reason("viewer", "no SPOILER please") == "word"
    assert hub.hidden_reason("viewer", "a bad word here") == "word"
    assert hub.hidden_reason("viewer", "spoilers are fine, so is badword") == ""       # whole words only
    with pytest.raises(ValueError):
        hub.clean_filters({"words": ["x" * 51]})
    with pytest.raises(ValueError):
        hub.clean_filters({"users": "everyone"})
    hub.publish("twitch", "troll", "hello")
    assert hub.messages[-1]["hidden"] == "user"
    hub.FILTERS = hub.clean_filters({"bots": False})
    assert hub.hidden_reason("Nightbot", "Follow the stream!") == ""


def test_first_time_chatters_and_health(fresh):
    fresh()
    hub.set_status("twitch", "on")
    assert hub.health["twitch"]["since"] > 0
    hub.publish("twitch", "Newbie", "hi")
    hub.publish("twitch", "newbie", "hi again")
    hub.publish("youtube", "Newbie", "same name, other platform")
    hub.publish("twitch", "Regular", "first ever here", first="ever")
    flags = [m.get("first") for m in list(hub.messages)[-4:]]
    assert flags == ["stream", None, "stream", "ever"]
    assert hub.health["twitch"]["last"] > 0
    hub.set_status("twitch", "retry")
    hub.set_status("twitch", "on")
    assert hub.health["twitch"]["reconnects"] == 1 and "health" in hub.status_event()


# ---- reading chat aloud ----------------------------------------------------------------------------------------
def test_what_gets_read_aloud(fresh):
    fresh()
    hub.EMOTES.update({"KEKW": "https://cdn.7tv.app/emote/1/2x.webp"})
    hub.TTS = hub.clean_tts({"enabled": True, "read": "questions", "max_chars": 9999, "rate": 7, "volume": -1})
    assert hub.TTS["max_chars"] == 500 and hub.TTS["rate"] == 2.0 and hub.TTS["volume"] == 0.0
    q = message("how do you do this? KEKW https://evil.example/x", question=True)
    assert hub.speech(q) == "viewer says: how do you do this? a link"
    assert hub.speech(message("just chatting")) == ""
    assert hub.speech({**q, "hidden": "word"}) == ""                       # filtered lines are never read
    assert hub.speech({**q, "badges": ["broadcaster"]}) == ""              # nor the streamer's own
    hub.TTS = hub.clean_tts({"enabled": True, "read": "command", "command": "!say", "names": False})
    assert hub.speech(message("!say hello there")) == "hello there" and hub.speech(message("hello")) == ""
    hub.TTS = hub.clean_tts({"enabled": True, "read": "events"})
    assert hub.speech({"kind": "event", "p": "twitch", "system": "Ann subscribed", "text": "love it"}) == "Ann subscribed. love it"
    hub.TTS = hub.clean_tts({"enabled": False})
    assert hub.speech(q) == "" and hub.speech(q, force=True)


def test_only_the_speaker_window_hears_it(fresh):
    fresh()
    speaker, other = asyncio.Queue(), asyncio.Queue()
    hub.clients.update({speaker, other})
    hub.state["speaker"] = speaker
    hub.TTS = hub.clean_tts({"enabled": True, "read": "all"})
    hub.publish("twitch", "viewer", "hello")
    said = [e for e in (speaker.get_nowait() for _ in range(speaker.qsize())) if e["type"] == "say"]
    assert said and said[0]["text"] == "viewer says: hello"
    assert not [e for e in (other.get_nowait() for _ in range(other.qsize())) if e["type"] == "say"]


# ---- what other websites and other devices may reach -----------------------------------------------------------------
CROSS_SITE = {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}


def test_other_websites_get_nothing_and_own_overlays_get_the_public_chat(fresh):
    fresh()
    hub.publish("twitch", "viewer", "hello")
    hub.FILTERS = hub.clean_filters({"users": ["troll"]})
    hub.publish("twitch", "troll", "filtered line")
    hub.note("OBS WebSocket at 127.0.0.1:4455")
    overlay_page = {"Origin": "http://localhost:%d", "Sec-Fetch-Site": "cross-site"}

    async def test(port):
        for path in ("/events", "/settings", "/themes", "/version", "/", "/studio"):
            assert (await http(port, "GET", path, CROSS_SITE))[0] == 403, path
        assert (await http(port, "GET", "/events", {"Origin": "null", "Sec-Fetch-Site": "cross-site"}))[0] == 403
        mine = {**overlay_page, "Origin": overlay_page["Origin"] % port}
        status, _, payload = await http(port, "GET", "/events?executor=1&speaker=1", mine, read=1 << 20)
        events = events_in(payload)
        assert status == 200 and {e["type"] for e in events} <= set(hub.PUBLIC_EVENTS)
        texts = [e.get("text") for e in events if e["type"] == "msg"]
        assert "hello" in texts and "filtered line" not in texts and not any("WebSocket" in (t or "") for t in texts)
        assert hub.state["executor"] is None and hub.state["speaker"] is None
        same = {"Host": "localhost:%d" % port, "Sec-Fetch-Site": "same-origin"}  # an overlay page asking its own address
        status, _, payload = await http(port, "GET", "/events?executor=1&speaker=1", same, read=1 << 20)
        assert status == 200 and {e["type"] for e in events_in(payload)} <= set(hub.PUBLIC_EVENTS)
        assert hub.state["executor"] is None and hub.state["speaker"] is None
        _, _, payload = await http(port, "GET", "/events", read=1 << 20)        # the hub's own pages get everything
        assert {"filters", "tts", "kick_auth", "devices"} <= {e["type"] for e in events_in(payload)}
        for path in ("/logs", "/feature?clear=1", "/show"):
            assert (await http(port, "GET", path, CROSS_SITE))[0] == 403, path
            assert (await http(port, "GET", path, mine))[0] == 403, path
        assert (await http(port, "GET", "/logs", {"Origin": "http://127.0.0.1:%d" % port, "Sec-Fetch-Site": "same-site"}))[0] == 403
        for path in ("/filters", "/tts", "/kick/connect", "/tts/say", "/send"):
            assert (await post(port, path, {}, {**CROSS_SITE, "Content-Type": "application/json"}))[0] == 403, path
            assert (await post(port, path, {}, {**mine, "Content-Type": "application/json"}))[0] == 403, path
    run(serving(test))


def test_public_feed_turns_filtering_into_deletion():
    feed = hub.PublicFeed()
    feed.put_nowait({"type": "hide", "id": "a", "why": "word"})
    feed.put_nowait({"type": "msg", "id": "b", "p": "twitch", "kind": "chat", "hidden": "user"})
    feed.put_nowait({"type": "feature", "msg": {"id": "c", "hidden": "word"}})
    feed.put_nowait({"type": "filters", "settings": {}})
    feed.put_nowait({"type": "msg", "id": "d", "p": "twitch", "kind": "chat"})
    assert [feed.get_nowait() for _ in range(feed.qsize())] == [{"type": "delete", "id": "a"},
                                                                {"type": "msg", "id": "d", "p": "twitch", "kind": "chat"}]


def test_a_newer_window_does_not_push_the_real_one_out(fresh):
    fresh()
    real, popup = asyncio.Queue(), asyncio.Queue()
    hub.take_role("executor", real)
    hub.take_role("executor", popup)
    assert hub.state["executor"] is popup
    assert hub.drop_role("executor", popup) and hub.state["executor"] is real        # back to the real window
    assert hub.drop_role("executor", real) and hub.state["executor"] is None


def test_filtered_messages_are_never_featured_or_read(fresh):
    fresh()
    hub.FILTERS = hub.clean_filters({"words": ["slur"]})
    hub.publish("twitch", "viewer", "a slur here")
    bad = hub.messages[-1]["id"]
    assert hub.feature(bad) is False and hub.state["featured"] is None
    hub.state["speaker"] = asyncio.Queue()

    async def test(port):
        answer = json.loads((await post(port, "/tts/say", {"id": bad}))[2])
        assert answer["ok"] is False and "filters" in answer["why"]
    run(serving(test))


def test_strange_viewer_counts_show_as_unknown(fresh, monkeypatch):
    fresh({"twitch": "somechannel"})
    monkeypatch.setattr(hub, "TWITCH", "somechannel")
    monkeypatch.setattr(hub, "twitch_viewers", lambda name: {"not": "a number"})
    hub.streaming.set()

    async def once():
        task = asyncio.create_task(hub.audience())
        await asyncio.sleep(0.2)
        task.cancel()
    run(once())
    hub.streaming.clear()
    assert hub.viewers["twitch"] is None and hub.viewer_event()["total"] == 0


def test_huge_requests_are_dropped(fresh):
    fresh()

    async def test(port):
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n" + b"X-Pad: aaaaaaaaaaaaaaaaaaaa\r\n" * 200)
        await writer.drain()
        assert await asyncio.wait_for(reader.read(), 5) == b""           # closed, no answer
        writer.close()
    run(serving(test, remote=True))


def test_companion_stays_off_when_windows_cannot_say(fresh, monkeypatch):
    fresh()
    monkeypatch.setattr(hub, "warn", lambda text: None)
    monkeypatch.setattr(hub, "lan_ip", lambda: "192.168.50.7")
    monkeypatch.setattr(hub, "network_category", lambda ip: "")
    monkeypatch.setattr(hub, "remote_why", "")
    hub.DEV.start_pairing()
    run(hub.remote_on())
    said = "macOS doesn't tell apps" if hub.MAC else "Linux doesn't tell apps" if hub.LINUX else "couldn't ask Windows"
    assert hub.remote_server is None and said in hub.remote_why


def test_removing_the_last_device_closes_the_companion(fresh, monkeypatch):
    fresh()
    closed = []

    class Server:
        def close(self):
            closed.append(True)

    monkeypatch.setattr(hub, "remote_server", Server())
    token = hub.DEV.pair(hub.DEV.start_pairing()[0], "Phone")
    hub.DEV.code = None
    device = hub.DEV.check(token)

    async def test(port):
        assert json.loads((await post(port, "/devices/revoke", {"id": device["id"]}))[2]) == {"ok": True}
    run(serving(test))
    assert closed and hub.remote_server is None


def test_settings_are_saved_only_from_this_pc(fresh):
    folder = fresh()
    hub.publish("twitch", "viewer", "big spoiler ahead")
    earlier = hub.messages[-1]["id"]
    watcher = asyncio.Queue()
    hub.clients.add(watcher)

    async def test(port):
        answer = json.loads((await post(port, "/filters", {"words": ["spoiler"], "users": [], "hide_commands": False}))[2])
        assert answer == {"ok": True} and hub.FILTERS["words"] == ["spoiler"]
        hidden = [e for e in (watcher.get_nowait() for _ in range(watcher.qsize())) if e["type"] == "hide"]
        assert hidden == [{"type": "hide", "id": earlier, "why": "word"}]          # what was already on screen goes too
        assert json.loads((folder / "filters.json").read_text())["words"] == ["spoiler"]
        answer = json.loads((await post(port, "/filters", {"words": "spoiler"}))[2])
        assert answer["ok"] is False and hub.FILTERS["words"] == ["spoiler"]
        assert json.loads((await post(port, "/tts", {"enabled": True, "read": "all"}))[2]) == {"ok": True}
        assert json.loads((folder / "tts.json").read_text())["read"] == "all"
        status, _, body = await http(port, "GET", "/logs")
        assert status == 200 and "logs" in json.loads(body)
    run(serving(test))


def test_paired_devices_cannot_change_settings_or_read_history(fresh):
    fresh()

    async def test(port):
        code, _ = hub.DEV.start_pairing()
        _, head, _ = await http(port, "GET", "/pair?code=" + code)
        cookie = {"Cookie": "cc_device=" + head.split("cc_device=")[1].split(";")[0]}
        for path in ("/logs", "/logs/2026-01-01_0000.csv", "/kick/callback?code=x&state=y"):
            assert (await http(port, "GET", path, cookie))[0] == 403, path
        for path in ("/filters", "/tts", "/kick/connect", "/kick/disconnect"):
            assert (await post(port, path, {}, same_origin(port, cookie)))[0] == 403, path
        answer = json.loads((await post(port, "/tts/say", {"id": "nope"}, same_origin(port, cookie)))[2])
        assert answer["ok"] is False                       # only messages from the chat can be read, never typed text
    run(serving(test, remote=True))


def test_companion_needs_a_plain_ip_address(fresh):
    fresh()

    async def test(port):
        code, _ = hub.DEV.start_pairing()
        rebound = {"Host": "evil.example:%d" % port}
        assert (await http(port, "GET", "/pair?code=" + code, rebound))[0] == 403
        assert (await http(port, "GET", "/", rebound))[0] == 403
        assert hub.DEV.pairing_open()                     # the code wasn't used up
    run(serving(test, remote=True))


def test_companion_stays_off_on_public_networks(fresh, monkeypatch):
    fresh()
    warned = []
    monkeypatch.setattr(hub, "warn", warned.append)
    monkeypatch.setattr(hub, "lan_ip", lambda: "192.168.50.7")
    monkeypatch.setattr(hub, "network_category", lambda ip: "Public")
    monkeypatch.setattr(hub, "remote_why", "")
    hub.DEV.start_pairing()

    async def test(port):
        answer = json.loads((await post(port, "/pair/start", {}))[2])
        assert answer["ok"] is False and "Public" in answer["why"] and hub.remote_server is None
        assert warned == [hub.PUBLIC_NETWORK]
    run(serving(test))
    monkeypatch.setattr(hub, "network_category", lambda ip: "Private")
    started = []

    async def fake_server(handler, address, port):
        started.append(address)
        return "server"

    monkeypatch.setattr(hub.asyncio, "start_server", fake_server)
    run(hub.remote_on())
    assert started == ["192.168.50.7"] and hub.remote_why == ""        # this network only, never 0.0.0.0
    hub.remote_server = None


# ---- Kick -----------------------------------------------------------------------------------------------------------
class Answer:
    def __init__(self, status, data):
        self.status_code, self.data, self.text = status, data, json.dumps(data)

    def json(self):
        return self.data


@pytest.mark.keyring
def test_kick_sign_in_needs_the_state_it_started(tmp_path, monkeypatch):
    k = kick_api.Kick("cid", "secret", str(tmp_path / "kick.bin"), "http://localhost:4466/kick/callback")
    asked = []
    monkeypatch.setattr(kick_api.requests, "post", lambda url, **kw: asked.append((url, kw)) or Answer(200, {
        "access_token": "AT-123", "refresh_token": "RT-456"}))
    monkeypatch.setattr(kick_api.Kick, "call", lambda self, *a, **kw: {"data": [{"user_id": 7, "name": "streamer"}]})
    with pytest.raises(kick_api.KickError):
        k.finish("code", "guess")                           # nothing started yet
    url = urllib.parse.urlsplit(k.start())
    query = urllib.parse.parse_qs(url.query)
    assert url.netloc == "id.kick.com" and query["code_challenge_method"] == ["S256"] and "client_secret" not in query
    with pytest.raises(kick_api.KickError):
        k.finish("code", query["state"][0] + "x")
    assert not asked
    k.finish("code", query["state"][0])
    assert asked[0][1]["data"]["code_verifier"] and k.state() == {"state": "on", "login": "streamer"}
    stored = (tmp_path / "kick.bin").read_bytes()
    assert b"AT-123" not in stored and b"RT-456" not in stored          # encrypted for this Windows user
    with pytest.raises(kick_api.KickError):
        k.finish("code", query["state"][0])                 # a state works once
    assert kick_api.Kick("cid", "", str(tmp_path / "kick.bin"), "").on()


def test_sign_outs_are_revoked_and_checked(tmp_path, monkeypatch):
    k = kick_api.Kick("cid", "", str(tmp_path / "kick.bin"), "")
    k.tokens = {"access_token": "AT", "refresh_token": "RT"}
    asked = []
    monkeypatch.setattr(kick_api.requests, "post", lambda url, **kw: asked.append((url, kw)) or Answer(200, {}))
    assert k.forget() is True and not k.on()
    assert [kw["params"] for _, kw in asked] == [{"token": "RT", "token_hint_type": "refresh_token"},
                                                 {"token": "AT", "token_hint_type": "access_token"}]
    k.tokens = {"access_token": "AT"}
    monkeypatch.setattr(kick_api.requests, "post", lambda url, **kw: Answer(500, {}))
    assert k.forget() is False and not k.on()                       # gone from this PC either way
    tw = twitch_api.Twitch("cid", str(tmp_path / "twitch.bin"))
    tw.tokens = {"access_token": "AT"}
    monkeypatch.setattr(twitch_api.requests, "post", lambda url, **kw: Answer(503, {}))
    assert tw.forget() is False


def test_twitch_sign_in_page_is_always_twitch(tmp_path, monkeypatch):
    tw = twitch_api.Twitch("cid", str(tmp_path / "twitch.bin"))
    monkeypatch.setattr(twitch_api.requests, "post", lambda url, **kw: Answer(200, {
        "device_code": "d", "user_code": "ABCD", "verification_uri": "javascript:alert(1)", "expires_in": 600, "interval": 5}))
    tw.start()
    assert tw.state()["verification_uri"] == "https://www.twitch.tv/activate"


def test_kick_moderation_requests(tmp_path, monkeypatch):
    k = kick_api.Kick("cid", "", str(tmp_path / "kick.bin"), "")
    k.tokens, k.broadcasters = {"access_token": "t"}, {"": 99}
    calls = []
    monkeypatch.setattr(kick_api.Kick, "call", lambda self, method, path, params=None, body=None, retry=True:
                        calls.append((method, path, body)) or {"data": {"is_sent": True}})
    k.send("", "hi", "parent-1")
    k.moderate("", "timeout", "5", seconds=90)
    k.moderate("", "timeout", "5", seconds=10 ** 9)
    k.moderate("", "ban", "5", reason="r" * 300)
    k.moderate("", "unban", "5")
    k.moderate("", "delete", message_id="../users?x=1")
    assert calls[0] == ("POST", "/chat", {"content": "hi", "type": "user", "broadcaster_user_id": 99, "reply_to_message_id": "parent-1"})
    assert calls[1][2]["duration"] == 2 and calls[2][2]["duration"] == 10080
    assert len(calls[3][2]["reason"]) == 100 and "duration" not in calls[3][2]
    assert calls[4][:2] == ("DELETE", "/moderation/bans")
    assert calls[5][:2] == ("DELETE", "/chat/..%2Fusers%3Fx%3D1")
    with pytest.raises(ValueError):
        k.moderate("", "ban", "not-a-number")


def test_kick_callback_page_is_escaped(fresh):
    fresh()

    async def test(port):
        status, _, page = await http(port, "GET", "/kick/callback?error=%3Cscript%3Ealert(1)%3C/script%3E")
        assert status == 200 and b"<script>" not in page and b"&lt;script&gt;" in page
        status, _, page = await http(port, "GET", "/kick/callback?code=abc&state=forged", CROSS_SITE)
        assert status == 200 and b"was not connected" in page and not hub.KK.on()
    run(serving(test))


def test_new_files_are_served(fresh):
    fresh()

    async def test(port):
        assert (await http(port, "GET", "/web/feed.js"))[0] == 200
        status, head, body = await http(port, "GET", "/favicon.ico")
        assert status == 200 and "image/x-icon" in head and body
    run(serving(test))
