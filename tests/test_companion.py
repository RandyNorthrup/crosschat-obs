"""The companion: paired devices, who may do what on the home-network port, and replies and moderation as jobs."""
import asyncio
import json
import time

import devices
import hub
import twitch_api


def run(job):
    return asyncio.run(job)


async def serving(test, remote=False):
    """The hub on a free port of this PC; remote=True serves it the way the companion port does."""
    server = await asyncio.start_server(lambda r, w: hub.serve(r, w, remote=remote), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    if not remote:
        hub.PORT = port
    async with server:
        return await test(port)


async def http(port, method, path, headers=None, body=b"", read=65536):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    head = {"Host": "127.0.0.1:%d" % port, "Content-Length": str(len(body)), **(headers or {})}
    writer.write(("%s %s HTTP/1.1\r\n" % (method, path) + "".join("%s: %s\r\n" % kv for kv in head.items()) + "\r\n").encode() + body)
    await writer.drain()
    data = b""
    try:
        while len(data) < read:
            chunk = await asyncio.wait_for(reader.read(read), 1)
            if not chunk:
                break
            data += chunk
    except asyncio.TimeoutError:
        pass
    writer.close()
    status, _, rest = data.partition(b"\r\n")
    head_text, _, payload = rest.partition(b"\r\n\r\n")
    return int(status.split()[1]) if status else 0, head_text.decode("latin1"), payload


def same_origin(port, extra=None):
    return {"Origin": "http://127.0.0.1:%d" % port, "Content-Type": "application/json", **(extra or {})}


def post(port, path, data, headers=None):
    return http(port, "POST", path, headers or same_origin(port), json.dumps(data).encode())


def drain(queue):
    return [queue.get_nowait() for _ in range(queue.qsize())]


# ---- devices ------------------------------------------------------------------------------------------------
def test_pairing_codes(tmp_path):
    d = devices.Devices(str(tmp_path / "devices.json"))
    assert d.pair("123456", "x") is None                         # nothing is open yet
    code, expires = d.start_pairing()
    assert len(code) == 6 and code.isdigit() and expires > time.time()
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(devices.CODE_TRIES - 1):
        assert d.pair(wrong, "x") is None
    token = d.pair(code, "Phone")
    assert token and d.pair(code, "again") is None              # a code works once
    stored = (tmp_path / "devices.json").read_text()
    assert token not in stored and devices.digest(token) in stored  # only the hash is kept
    found = d.check(token)
    assert found["name"] == "Phone" and devices.Devices(str(tmp_path / "devices.json")).check(token)
    assert d.revoke(found["id"]) and d.check(token) is None


def test_too_many_wrong_codes_close_pairing(tmp_path):
    d = devices.Devices(str(tmp_path / "devices.json"))
    code, _ = d.start_pairing()
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(devices.CODE_TRIES):
        d.pair(wrong, "x")
    assert d.pair(code, "x") is None and not d.pairing_open()


def test_device_names():
    assert devices.device_name("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)") == "iPhone"
    assert devices.device_name("Mozilla/5.0 (Linux; Android 15; Pixel 9)") == "Android"
    assert devices.device_name("") == "Device"


def test_twitch_tokens_are_encrypted_for_this_windows_user(tmp_path):
    secret = b'{"access_token": "abc"}'
    sealed = twitch_api.protect(secret)
    assert secret not in sealed and twitch_api.unprotect(sealed) == secret
    t = twitch_api.Twitch("client", str(tmp_path / "twitch.bin"))
    t.tokens, t.user = {"access_token": "tok", "refresh_token": "ref"}, {"id": "1", "login": "me"}
    t.save()
    assert b"tok" not in (tmp_path / "twitch.bin").read_bytes()
    again = twitch_api.Twitch("client", str(tmp_path / "twitch.bin"))
    assert again.on() and again.state() == {"state": "on", "login": "me"}
    assert twitch_api.Twitch("", str(tmp_path / "none.bin")).state()["state"] == "off"


# ---- the companion port ---------------------------------------------------------------------------------------
def test_unpaired_devices_get_only_the_pairing_page(home):
    home()

    async def test(port):
        status, _, page = await http(port, "GET", "/")
        assert status == 200 and b"Pair with CrossChat" in page
        assert (await http(port, "GET", "/events"))[0] == 401
        assert (await http(port, "GET", "/whoami"))[0] == 401
        status, head, body = await post(port, "/pair", {"code": "123456"})
        assert json.loads(body)["ok"] is False and "Set-Cookie" not in head
    run(serving(test, remote=True))


def test_pairing_then_using_the_companion(home):
    home()

    async def test(port):
        code, _ = hub.DEV.start_pairing()
        status, head, _ = await http(port, "GET", "/pair?code=" + code, {"User-Agent": "Mozilla/5.0 (iPhone)"})
        assert status == 303 and "Location: /" in head and "HttpOnly" in head and "SameSite=Strict" in head
        token = head.split("cc_device=")[1].split(";")[0]
        cookie = {"Cookie": "cc_device=" + token}
        who = json.loads((await http(port, "GET", "/whoami", cookie))[2])
        assert who["remote"] is True and who["device"] == "iPhone"
        assert (await http(port, "GET", "/", cookie))[0] == 200
        assert (await http(port, "GET", "/web/app.js", cookie))[0] == 200
        # things only the streaming PC may do
        for path in ("/show", "/x/go?mode=dry", "/studio", "/overlay/chat"):
            assert (await http(port, "GET", path, cookie))[0] == 403, path
        for path in ("/pair/start", "/devices/revoke", "/twitch/connect", "/themes/save", "/outbox/result"):
            assert (await post(port, path, {}, same_origin(port, cookie)))[0] == 403, path
        # changes must come from the companion page itself
        assert (await post(port, "/star", {"id": "x", "on": True}, {**cookie, "Origin": "http://evil.example",
                                                                         "Content-Type": "application/json"}))[0] == 403
        assert json.loads((await post(port, "/star", {"id": "x", "on": True}, same_origin(port, cookie)))[2]) == {"ok": True}
        hub.DEV.revoke(hub.DEV.devices[0]["id"])
        assert (await http(port, "GET", "/whoami", cookie))[0] == 401
    run(serving(test, remote=True))


# ---- replies and moderation as jobs -------------------------------------------------------------------------
def test_replies_go_through_the_executor(home):
    home()

    async def test(port):
        executor = asyncio.Queue()
        hub.clients.add(executor)
        hub.state["executor"] = executor
        answer = json.loads((await post(port, "/send", {"to": ["youtube", "x"], "text": "  hello   there ", "reply": None}))[2])
        assert answer["ok"] and answer["job_id"]
        await asyncio.sleep(0.05)
        job = next(e["job"] for e in drain(executor) if e["type"] == "outbox")
        assert job["text"] == "hello there" and job["to"] == ["youtube", "x"] and job["id"] == answer["job_id"]
        await post(port, "/outbox/result", {"job_id": job["id"], "answer": {"youtube": {"ok": True}, "x": {"ok": False, "why": "nope"}}})
        await asyncio.sleep(0.05)
        sent = next(e for e in drain(executor) if e["type"] == "sent")
        assert sent["job_id"] == job["id"] and sent["answer"] == {"youtube": {"ok": True}, "x": {"ok": False, "why": "nope"}}
    run(serving(test))


def test_replies_without_the_chat_window_say_why(home):
    home()

    async def test(port):
        watcher = asyncio.Queue()
        hub.clients.add(watcher)
        await post(port, "/send", {"to": ["youtube"], "text": "hi"})
        await asyncio.sleep(0.05)
        sent = next(e for e in drain(watcher) if e["type"] == "sent")
        assert sent["answer"]["youtube"] == {"ok": False, "why": hub.NO_EXECUTOR}
        assert json.loads((await post(port, "/send", {"to": ["x"], "text": "x" * 141}))[2])["why"] == "too long for X"
        await post(port, "/send", {"to": ["kick"], "text": "hi"})
        await asyncio.sleep(0.05)
        sent = next(e for e in drain(watcher) if e["type"] == "sent")
        assert sent["answer"]["kick"] == {"ok": False, "why": "Connect Kick in Settings to reply on Kick"}
    run(serving(test))


class FakeTwitch:
    client_id = "c"

    def __init__(self):
        self.sent, self.modded = [], []

    def on(self):
        return True

    def state(self):
        return {"state": "on", "login": "me"}

    def send(self, channel, text, parent=""):
        self.sent.append((channel, text, parent))

    def moderate(self, channel, action, user_id, message_id, seconds, reason):
        self.modded.append((channel, action, user_id, message_id, seconds))


def test_twitch_goes_through_its_api(home):
    home({"twitch": "somechannel"})
    hub.TW = FakeTwitch()

    async def test(port):
        watcher = asyncio.Queue()
        hub.clients.add(watcher)
        reply = {"p": "twitch", "id": "abc-123", "name": "Ann"}
        await post(port, "/send", {"to": ["twitch"], "text": "@Ann thanks!", "reply": reply})
        await post(port, "/mod", {"p": "twitch", "action": "timeout", "user_id": "42", "message_id": "m1", "seconds": 600})
        await asyncio.sleep(0.1)
        results = [e["answer"] for e in drain(watcher) if e["type"] == "sent"]
        assert {"twitch": {"ok": True}} in results and {"ok": True} in results
    run(serving(test))
    assert hub.TW.sent == [("somechannel", "thanks!", "abc-123")]          # threaded: Twitch adds the @name itself
    assert hub.TW.modded == [("somechannel", "timeout", "42", "m1", 600)]


def test_moderation_rules(home):
    home({"twitch": "somechannel"})

    async def test(port):
        watcher = asyncio.Queue()
        hub.clients.add(watcher)
        assert json.loads((await post(port, "/mod", {"p": "x", "action": "ban"}))[2])["ok"] is False
        assert json.loads((await post(port, "/mod", {"p": "youtube", "action": "unban"}))[2])["ok"] is False
        assert json.loads((await post(port, "/mod", {"p": "twitch", "action": "delete", "message_id": "m"}))[2])["ok"] is True
        await asyncio.sleep(0.05)
        sent = next(e for e in drain(watcher) if e["type"] == "sent")
        assert sent["answer"]["ok"] is False and "Connect Twitch" in sent["answer"]["why"]   # not connected yet
    run(serving(test))


def test_facebook_and_rumble_moderation_go_through_their_own_pages(home):
    home({"twitch": "somechannel"})

    async def test(port):
        executor = asyncio.Queue()
        hub.state["executor"] = executor
        hub.rumble_read({"livestreams": [{"id": "7fiazm", "is_live": True, "chat": {"recent_messages": [
            {"username": "Bo", "text": "spam spam", "created_on": "2026-11-01T01:27:34+00:00", "badges": []}]}}]}, [], {})
        hub.facebook_feed(lambda k: {"lines": json.dumps([{"id": "123_456", "name": "Cy", "text": "rude words"}])}.get(k, ""))
        rumble_mid = next(m["mid"] for m in hub.messages if m["p"] == "rumble")          # what the window would send
        # Rumble: the hub sends the extension the name and words it has (Rumble lines have no id), and only Rumble's
        # 5-minute mute counts as a timeout, whatever length the page asked for.
        assert json.loads((await post(port, "/mod", {"p": "rumble", "action": "timeout", "message_id": rumble_mid,
                                                     "name": "someone else", "seconds": 3600}))[2])["ok"] is True
        assert json.loads((await post(port, "/mod", {"p": "rumble", "action": "mute", "message_id": rumble_mid}))[2])["ok"] is True
        assert json.loads((await post(port, "/mod", {"p": "facebook", "action": "delete", "message_id": "fb-123_456"}))[2])["ok"] is True
        await asyncio.sleep(0.05)
        outbox = [e["job"] for e in drain(executor) if e["type"] == "outbox"]
        assert [(j["p"], j["action"]) for j in outbox] == [("rumble", "timeout"), ("rumble", "mute"), ("facebook", "delete")]
        assert outbox[0]["name"] == "Bo" and outbox[0]["text"] == "spam spam" and outbox[0]["seconds"] == 300
        assert outbox[2]["message_id"] == "fb-123_456"
        # A line the hub no longer has, and what these pages can't do, are refused up front.
        gone = json.loads((await post(port, "/mod", {"p": "rumble", "action": "delete", "message_id": "rm-nope"}))[2])
        assert gone["ok"] is False and "no longer" in gone["why"]
        assert json.loads((await post(port, "/mod", {"p": "facebook", "action": "ban"}))[2])["ok"] is False
        assert json.loads((await post(port, "/mod", {"p": "rumble", "action": "unban"}))[2])["ok"] is False
        hub.state["executor"] = None
    run(serving(test))


def test_demo_mode_answers_everything_on_this_pc(home, tmp_path):
    (tmp_path / "devices.json").write_text('{"devices": [{"id": "real", "name": "My phone", "hash": "x"}]}')
    folder = home({"twitch": "realchannel"}, "--demo")
    assert hub.DEMO and hub.TEST and hub.twitch_event()["state"] == "on"
    assert hub.DEV.listing() == []                         # real device names stay out of demo screenshots

    async def test(port):
        watcher = asyncio.Queue()
        hub.clients.add(watcher)
        hub.publish("youtube", "Sam", "spam spam", raw="m1", uid="u1", mid="yt-m1")
        await post(port, "/send", {"to": ["twitch", "youtube", "x"], "text": "thanks all"})
        await post(port, "/mod", {"p": "youtube", "action": "delete", "message_id": "m1"})
        await asyncio.sleep(1.5)
        events = drain(watcher)
        echoes = [e for e in events if e["type"] == "msg" and e["name"] == "you"]
        assert sorted(e["p"] for e in echoes) == ["twitch", "x", "youtube"]
        assert {"type": "delete", "id": "yt-m1"} in events
        assert all(a["answer"] == {"twitch": {"ok": True}, "youtube": {"ok": True}, "x": {"ok": True}} or a["answer"] == {"ok": True}
                   for a in events if a["type"] == "sent")
        assert json.loads((await post(port, "/pair/start", {}))[2])["ok"] is False
        # the demo never touches the real accounts, devices or settings
        for path in ("/twitch/disconnect", "/kick/disconnect", "/twitch/connect", "/kick/connect", "/devices/revoke"):
            assert json.loads((await post(port, path, {"id": "x"}))[2])["ok"] is False, path
        assert json.loads((await post(port, "/filters", {"words": ["demo"]}))[2])["ok"] is True
        assert (folder / "filters-demo.json").exists() and not (folder / "filters.json").exists()
    run(serving(test))


def test_quick_replies_stars_and_questions(home):
    folder = home()

    async def test(port):
        watcher = asyncio.Queue()
        hub.clients.add(watcher)
        assert hub.quick_replies() == hub.QUICK_DEFAULTS
        assert json.loads((await post(port, "/quick", {"replies": ["GG", "  hi   all "]}))[2]) == {"ok": True}
        assert hub.quick_replies() == ["GG", "hi all"] and (folder / "quick.json").exists()
        assert json.loads((await post(port, "/quick", {"replies": ["x" * 101]}))[2])["ok"] is False
        hub.publish("twitch", "ann", "what keyboard is that?", mid="tw-q")
        hub.publish("twitch", "bob", "nice stream", mid="tw-n")
        assert hub.messages[-2].get("question") is True and "question" not in hub.messages[-1]
        await post(port, "/star", {"id": "tw-q", "on": True})
        await post(port, "/star", {"id": "missing", "on": True})
        assert hub.starred == ["tw-q"]
        await post(port, "/star", {"id": "tw-q", "on": False})
        assert hub.starred == []
    run(serving(test))
