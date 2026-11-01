"""The update notice (opt-in), the companion on Tailscale (opt-in), and posting to Discord through a webhook."""
import asyncio
import json
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

import config_file
import discord_relay
import hub
import tailscale
import updates
from test_companion import drain, http, post, run, same_origin, serving

HOOK_ID = "123456789012345678"
HOOK_TOKEN = "abcDEF123_-" * 6                         # made-up, the shape of a webhook token  # gitleaks:allow
HOOK = "https://discord.com/api/webhooks/%s/%s" % (HOOK_ID, HOOK_TOKEN)


@pytest.fixture(autouse=True)
def fresh():
    hub.update_state.update({"checked": 0.0, "found": None, "wake": None})
    yield
    for server in (hub.remote_server, hub.tailscale_server):
        if server:
            server.close()
    hub.remote_server = hub.tailscale_server = None
    hub.tailscale_address = hub.tailscale_seen = hub.tailscale_why = ""


# ---- the update notice --------------------------------------------------------------------------------------------
class Answer:
    def __init__(self, status=200, data=None, raw=None):
        self.status_code = status
        body = raw if raw is not None else json.dumps(data if data is not None else {}).encode()
        self.raw = type("Raw", (), {"read": lambda _self, n, decode_content=True: body[:n]})()
        self.closed = False

    def close(self):
        self.closed = True


def release(tag, **more):
    return {"tag_name": tag, "draft": False, "prerelease": False, "html_url": "https://evil.example/phish", **more}


def test_update_check_asks_one_fixed_address_and_builds_its_own_link():
    asked = []

    def get(url, **kw):
        asked.append((url, kw))
        return Answer(data=release("v1.7.0"))

    found = updates.newest("1.6.0", get)
    assert found == {"version": "1.7.0", "url": "https://github.com/RandyNorthrup/crosschat-obs/releases/tag/v1.7.0"}  # never html_url
    url, kw = asked[0]
    assert url == "https://api.github.com/repos/RandyNorthrup/crosschat-obs/releases/latest"
    assert kw["headers"] == {"User-Agent": "CrossChat/1.6.0", "Accept": "application/vnd.github+json"}   # nothing about the streamer
    assert kw["allow_redirects"] is False and kw["timeout"] and "cookies" not in kw
    assert updates.newest("1.7.0", lambda *a, **k: Answer(data=release("v1.7.0"))) is None               # this one
    assert updates.newest("1.10.0", lambda *a, **k: Answer(data=release("v1.9.9"))) is None              # older (not text order)
    assert updates.newest("1.6.0", lambda *a, **k: Answer(data=release("v1.7.0", prerelease=True))) is None
    assert updates.newest("1.6.0", lambda *a, **k: Answer(data=release("v1.7.0", draft=True))) is None


@pytest.mark.parametrize("answer", [Answer(500), Answer(301), Answer(raw=b"not json"), Answer(raw=b"x" * (updates.MOST + 5)),
                                    Answer(data=release("v1.7.0-rc1")), Answer(data=release("latest")), Answer(data=[1, 2])])
def test_update_check_refuses_odd_answers(answer):
    with pytest.raises(updates.UpdateError):
        updates.newest("1.6.0", lambda *a, **k: answer)


def test_update_check_never_puts_details_of_the_failure_in_its_message():
    def down(*a, **k):
        raise requests.ConnectionError("proxy.internal:3128 refused")

    with pytest.raises(updates.UpdateError) as error:
        updates.newest("1.6.0", down)
    assert "proxy" not in str(error.value) and error.value.__cause__ is None


def test_update_notice_is_off_until_switched_on_then_asks_once_a_day(home, monkeypatch):
    folder = home({})
    assert hub.CFG["updates"]["check"] is False and hub.update_event()["check"] is False
    asked = []

    def newest(version, get=None):
        asked.append(version)
        return {"version": "9.0.0", "url": updates.page((9, 0, 0))}

    monkeypatch.setattr(hub.updates, "newest", newest)

    async def test(port):
        watcher = asyncio.Queue()
        hub.local_clients.add(watcher)
        job = asyncio.create_task(hub.update_watch())
        await asyncio.sleep(0.1)
        assert asked == []                                          # off: GitHub is never asked
        assert json.loads((await post(port, "/updates", {"check": True}))[2]) == {"ok": True}
        await asyncio.sleep(0.2)
        assert asked == [hub.VERSION]
        event = [e for e in drain(watcher) if e["type"] == "update"][-1]
        assert event == {"type": "update", "check": True, "version": "9.0.0", "url": updates.page((9, 0, 0))}
        hub.update_state["wake"].set()                              # switched again: not twice in a day
        await asyncio.sleep(0.1)
        assert asked == [hub.VERSION]
        job.cancel()
    run(serving(test))
    assert json.loads((folder / "config.json").read_text())["updates"] == {"check": True}
    saved = json.loads((folder / "update-check.json").read_text())
    assert saved["checked"] > 0 and saved["found"]["version"] == "9.0.0"


def test_update_notice_never_shows_a_link_it_did_not_make(home):
    home({"updates": {"check": True}})
    hub.update_state["found"] = {"version": "9.0.0", "url": "https://evil.example/"}
    assert hub.update_event()["url"] == updates.page((9, 0, 0))
    hub.update_state["found"] = {"version": "0.1.0"}                 # older than this one: nothing
    assert hub.update_event()["version"] == ""


def test_config_switches_keep_everything_else(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"twitch": "me", "remote": {"port": 5000}, "mine": [1]}', encoding="utf-8")
    config_file.change(str(path), "remote.tailscale", True)
    config_file.change(str(path), "updates.check", False)
    assert json.loads(path.read_text()) == {"twitch": "me", "remote": {"port": 5000, "tailscale": True}, "mine": [1], "updates": {"check": False}}
    path.write_text("{ broken", encoding="utf-8")
    with pytest.raises(ValueError):
        config_file.change(str(path), "updates.check", True)
    assert path.read_text() == "{ broken"                            # left alone


# ---- Tailscale ------------------------------------------------------------------------------------------------------
class Ran:
    def __init__(self, stdout, code=0):
        self.stdout, self.returncode = stdout, code


def test_tailscale_is_off_on_a_mac_for_now(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert tailscale.address(lambda *a, **k: Ran("100.101.102.103")) == ""             # never asks, never listens there


@pytest.mark.skipif(sys.platform != "win32", reason="Tailscale for the companion is Windows-only for now")
def test_tailscale_address_only_from_tailscales_own_adapter():
    calls = []

    def run_(argv, **kw):
        calls.append(argv)
        return Ran("100.101.102.103\r\n")

    assert tailscale.address(run_) == "100.101.102.103"
    assert "Tailscale" in calls[0][-1] and "Get-NetAdapter" in calls[0][-1]           # asked by adapter, not by range
    assert tailscale.address(lambda *a, **k: Ran("192.168.1.5\n10.0.0.2\n")) == ""      # not Tailscale's range
    assert tailscale.address(lambda *a, **k: Ran("100.64.0.1", 1)) == ""                 # Windows said no
    assert tailscale.pick(["junk", "100.200.0.1", "100.64.0.9"]) == "100.64.0.9"         # 100.200 is outside 100.64.0.0/10

    def broken(*a, **k):
        raise OSError("no powershell")

    assert tailscale.address(broken) == ""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_companion_on_tailscale_is_opt_in_and_follows_tailscale(home, monkeypatch):
    port = free_port()
    home({"remote": {"port": port}})
    where = {"ip": "127.0.0.1"}                                 # stands in for the PC's Tailscale address
    monkeypatch.setattr(hub.tailscale, "address", lambda: where["ip"])
    monkeypatch.setattr(hub, "lan_on", lambda: asyncio.sleep(0))  # the home-network side is tested elsewhere

    async def test(app_port):
        watcher = asyncio.Queue()
        hub.local_clients.add(watcher)
        await post(app_port, "/pair/start", {})
        assert hub.tailscale_server is None                     # off unless switched on
        assert json.loads((await post(app_port, "/companion/tailscale", {"on": True}))[2]) == {"ok": True}
        assert hub.tailscale_server and hub.tailscale_url() == "http://127.0.0.1:%d/" % port
        answer = json.loads((await post(app_port, "/pair/start", {}))[2])
        assert answer["ok"] and answer["url"].startswith("http://127.0.0.1:%d/pair?code=" % port)
        assert (await http(port, "GET", "/events"))[0] == 401   # pairing still needed there
        where["ip"] = ""                                         # Tailscale stops
        await hub.companion_round(1)
        assert hub.tailscale_server is None
        event = [e for e in drain(watcher) if e["type"] == "companion"][-1]
        assert event["tailscale"] is True and event["listening"] is False
        where["ip"] = "127.0.0.1"                                # and comes back
        await hub.companion_round(2)
        assert hub.tailscale_server
        await post(app_port, "/companion/tailscale", {"on": False})
        assert hub.tailscale_server is None
        where["ip"] = ""
        await post(app_port, "/companion/tailscale", {"on": True})
        why = [e for e in drain(watcher) if e["type"] == "companion"][-1]["why"]
        assert "Tailscale isn't running" in why
    run(serving(test))


def test_tailscale_switch_is_this_pc_only(home):
    home({})

    async def remote(port):
        code, _ = hub.DEV.start_pairing()
        _, head, _ = await http(port, "GET", "/pair?code=" + code)
        cookie = {"Cookie": "cc_device=" + head.split("cc_device=")[1].split(";")[0]}
        for path in ("/companion/tailscale", "/updates", "/discord/connect", "/discord/test", "/discord/disconnect"):
            assert (await post(port, path, {"on": True}, same_origin(port, cookie)))[0] == 403, path
    run(serving(remote, remote=True))


# ---- Discord ---------------------------------------------------------------------------------------------------------
class FakeDiscord:
    """A local stand-in for discord.com: records posts, answers the way Discord does."""

    def __init__(self):
        self.posts, self.answers, self.gone = [], [], False
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def reply(self, code, data=None):
                body = json.dumps(data).encode() if data is not None else b""
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if fake.gone or self.path != "/api/webhooks/%s/%s" % (HOOK_ID, HOOK_TOKEN):
                    return self.reply(404, {"message": "Unknown Webhook", "code": 10015})
                self.reply(200, {"type": 1, "id": HOOK_ID, "name": "stream-chat", "channel_id": "1", "guild_id": "2"})

            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if fake.gone:
                    return self.reply(404, {"message": "Unknown Webhook", "code": 10015})
                if fake.answers:
                    code, body = fake.answers.pop(0)
                    return self.reply(code, body)
                fake.posts.append(data)
                self.reply(204)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def discord():
    fake = FakeDiscord()
    yield fake
    fake.close()


def chat(name, text, **more):
    return {"type": "msg", "id": "tw-1", "p": "twitch", "kind": "chat", "name": name, "text": text, **more}


def test_chat_reaches_discord_as_plain_text_that_pings_nobody():
    names = hub.NAMES
    line = discord_relay.line(chat("**boss**", "@everyone hi <@123> ||spoiler|| [click](https://evil.example) see https://x.example/a`b"), names)
    assert "@everyone" not in line and "@\u200beveryone" in line
    assert "<@123>" not in line and "\\<@\u200b123\\>" in line
    assert "\\|\\|spoiler\\|\\|" in line and "\\[click\\]" in line
    assert "`https://x.example/ab`" in line and "`https://evil.example)`" in line     # links shown, not clickable
    assert line.startswith("**\\*\\*boss\\*\\*** (Twitch): ")
    assert len(discord_relay.line(chat("a", "x" * 5000), names)) <= discord_relay.LINE_MOST
    assert discord_relay.shown(chat("a", "b")) and not discord_relay.shown(chat("a", "b", hidden="word"))
    assert not discord_relay.shown(chat("a", "b", test=True)) and not discord_relay.shown({"type": "msg", "p": "system", "kind": "note", "text": "x"})
    assert discord_relay.line({"p": "kick", "kind": "event", "name": "turbo", "system": "turbo gifted 5 subs", "text": ""}, names) == \
        "**turbo** (Kick) turbo gifted 5 subs"


@pytest.mark.keyring
def test_webhook_url_is_checked_encrypted_and_never_shown(tmp_path, discord, monkeypatch):
    d = discord_relay.Discord(str(tmp_path / "discord.bin"), hub.NAMES, base=discord.base)
    for bad in ("http://discord.com/api/webhooks/%s/%s" % (HOOK_ID, HOOK_TOKEN), "https://evil.example/api/webhooks/%s/%s" % (HOOK_ID, HOOK_TOKEN),
                "https://discord.com.evil.example/api/webhooks/%s/%s" % (HOOK_ID, HOOK_TOKEN), HOOK + "?x=1", HOOK + "/extra",
                "https://discord.com/api/webhooks/abc/%s" % HOOK_TOKEN, "not a url"):
        with pytest.raises(discord_relay.DiscordError):
            d.set(bad)
    with pytest.raises(discord_relay.DiscordError):             # well formed, but Discord doesn't know it
        d.set("https://discord.com/api/webhooks/%s/%s" % (HOOK_ID, "z" * 68))
    assert not d.on()
    d.set(HOOK, {"chat": True})
    assert d.on() and d.state() == {"state": "on", "why": "", "name": "stream-chat", "live": True, "featured": True, "chat": True}
    assert HOOK_TOKEN.encode() not in (tmp_path / "discord.bin").read_bytes()               # encrypted for this Windows user
    again = discord_relay.Discord(str(tmp_path / "discord.bin"), hub.NAMES)
    assert again.url == HOOK and again.choices["chat"] is True and HOOK_TOKEN not in json.dumps(again.state())

    def down(*a, **k):
        raise requests.ConnectionError("could not reach " + HOOK)

    monkeypatch.setattr(discord_relay.requests, "post", down)
    with pytest.raises(discord_relay.DiscordError) as error:
        again.post({"content": "x"})
    assert HOOK_TOKEN not in str(error.value) and error.value.__cause__ is None
    again.forget()
    assert not (tmp_path / "discord.bin").exists() and again.state()["state"] == "off"


@pytest.mark.keyring
def test_posting_batches_waits_when_asked_and_stops_when_the_webhook_is_gone(tmp_path, discord):
    changed = []
    d = discord_relay.Discord(str(tmp_path / "discord.bin"), hub.NAMES, base=discord.base, changed=lambda: changed.append(1))
    d.set(HOOK, {"chat": True})
    for i in range(30):
        d.chat(chat("viewer%d" % i, "message %d" % i))
    d.chat(chat("filtered", "nope", hidden="user"))
    d.featured(chat("star", "on stream now"))
    d.live("🔴 **Live now!**\nTwitch: https://www.twitch.tv/me")
    discord.answers.append((429, {"message": "You are being rate limited.", "retry_after": 0.05, "global": False}))
    slept = []

    async def sleep(seconds):
        slept.append(seconds)
        await asyncio.sleep(0)

    async def test():
        job = asyncio.create_task(d.run(sleep))
        for _ in range(200):
            await asyncio.sleep(0.02)
            if len(discord.posts) >= 3:
                break
        job.cancel()
    run(test())
    lines, featured, live = discord.posts[:3]
    assert lines["content"].count("\n") == 29 and "filtered" not in lines["content"] and len(lines["content"]) <= 2000
    assert all(p["allowed_mentions"] == {"parse": []} for p in discord.posts)
    assert lines["flags"] == discord_relay.SUPPRESS_EMBEDS | discord_relay.SUPPRESS_NOTIFICATIONS
    assert featured["content"].startswith("⭐ On stream: **star**") and live["content"].startswith("🔴")
    assert 0.05 in slept and discord_relay.GAP in slept                # waited as Discord asked, and between posts

    discord.gone = True
    d.chat(chat("late", "anyone?"))

    async def gone():
        job = asyncio.create_task(d.run(sleep))
        for _ in range(100):
            await asyncio.sleep(0.02)
            if changed:
                break
        job.cancel()
    run(gone())
    assert changed and d.state()["state"] == "error" and "deleted" in d.state()["why"]
    d.chat(chat("after", "nothing queued"))
    assert not d.waiting


def test_chat_faster_than_discord_drops_the_oldest_lines_and_says_so(tmp_path):
    d = discord_relay.Discord(str(tmp_path / "discord.bin"), hub.NAMES)
    d.url, d.choices["chat"] = HOOK, True
    for i in range(discord_relay.BACKLOG + 100):
        d.chat(chat("v", "line %d" % i))
    assert d.lines == discord_relay.BACKLOG and d.dropped == 100
    first = d.next_post()
    assert first["content"].startswith("_(100 messages skipped") and "line 100\n" in first["content"] and "line 99\n" not in first["content"]


@pytest.mark.keyring
def test_hub_posts_to_discord_only_during_a_real_stream(home, discord):
    home({"twitch": "me", "youtube": "@mychannel", "kick": "me-too"})
    hub.DC.base = discord.base
    hub.DC.set(HOOK, {"chat": True})
    hub.streaming.clear()

    async def test():
        hub.publish("twitch", "before", "not live yet")
        assert not hub.DC.waiting
        await hub.stream_started()
        hub.publish("twitch", "ann", "hello Discord", mid="tw-a")
        hub.publish("twitch", "nightbot", "a bot line", mid="tw-b")          # hidden by the bots filter
        hub.feature("tw-a")
        kinds = [(k, t) for k, t, *_ in hub.DC.waiting]
        assert kinds[0][0] == "post" and "https://www.twitch.tv/me" in kinds[0][1] and "https://www.youtube.com/@mychannel/live" in kinds[0][1]
        assert "https://kick.com/me-too" in kinds[0][1]
        assert ("line", "**ann** (Twitch): hello Discord") in kinds and not any("bot line" in t for _, t in kinds)
        assert any(t.startswith("⭐ On stream: **ann**") for _, t in kinds)
        await hub.stream_stopped()
        hub.DC.clear()
        await hub.stream_started(local=True)                                 # a test stream to this PC: nothing
        hub.publish("twitch", "bob", "local test")
        assert not hub.DC.waiting
        await hub.stream_stopped()
    try:
        run(test())
    finally:
        hub.streaming.clear()
        if hub.closing:
            hub.closing.cancel()


@pytest.mark.keyring
def test_discord_routes(home, discord):
    home({})
    hub.DC.base = discord.base

    async def test(port):
        watcher = asyncio.Queue()
        hub.clients.add(watcher)
        assert json.loads((await post(port, "/discord/connect", {"url": "https://evil.example/api/webhooks/1/2"}))[2])["ok"] is False
        assert json.loads((await post(port, "/discord/connect", {"url": HOOK, "live": True, "featured": False, "chat": True}))[2]) == {"ok": True}
        assert hub.DC.choices == {"live": True, "featured": False, "chat": True}
        assert json.loads((await post(port, "/discord/options", {"featured": True}))[2]) == {"ok": True}
        assert hub.DC.choices["featured"] is True
        assert json.loads((await post(port, "/discord/test", {}))[2]) == {"ok": True}
        assert discord.posts[-1]["content"] == discord_relay.HELLO and discord.posts[-1]["allowed_mentions"] == {"parse": []}
        events = drain(watcher)
        assert {"type": "discord_auth", "state": "on", "why": "", "name": "stream-chat", "live": True, "featured": True, "chat": True} in events
        assert HOOK_TOKEN not in json.dumps(events) and HOOK_TOKEN not in json.dumps(hub.discord_event())   # the URL never leaves the hub
        assert json.loads((await post(port, "/discord/disconnect", {}))[2]) == {"ok": True} and not hub.DC.on()
    run(serving(test))


def test_demo_never_touches_discord_tailscale_or_updates(home):
    folder = home(None, "--demo")

    async def test(port):
        for path in ("/discord/connect", "/discord/test", "/discord/disconnect", "/companion/tailscale"):
            assert json.loads((await post(port, path, {"url": HOOK, "on": True}))[2])["ok"] is False, path
        assert json.loads((await post(port, "/updates", {"check": True}))[2]) == {"ok": True}
        assert hub.update_event()["check"] is False                        # the demo never asks GitHub
    run(serving(test))
    assert not (folder / "config.json").exists()
