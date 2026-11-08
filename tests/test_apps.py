"""The hub following Streamlabs Desktop, or a Start stream button, instead of OBS."""
import asyncio
import json
import re

import hub
import pytest
import settings_ui


class FakeStreamlabs:
    """Streamlabs Desktop's local API as its source has it: one JSON-RPC message per line, id required, no token here.
    `script` holds what each getModel answers: a status, None for no answer (loading), or "busy"."""

    def __init__(self, script, drop_after=None):
        self.script, self.drop_after, self.seen, self.connections = list(script), drop_after, [], 0
        self.server = None

    async def handle(self, reader, writer):
        self.connections += 1
        served = 0
        while self.script:
            line = await reader.readline()
            if not line:
                break
            request = json.loads(line)
            assert request["jsonrpc"] == "2.0" and request["id"] and request["method"] == "getModel"
            assert request["params"]["resource"] == "StreamingService"
            self.seen.append(hub.streaming.is_set())
            answer = self.script.pop(0)
            if answer == "busy":
                writer.write(b'{"jsonrpc":"2.0","id":null,"error":{"code":-32603,"message":"API server is busy. Try again later"}}\n')
            elif answer is not None:
                model = {"status": {}, "streamingStatus": answer, "recordingStatus": "offline", "replayBufferStatus": "offline"}
                writer.write((json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": model}) + "\n").encode())
            await writer.drain()
            served += 1
            if served == self.drop_after:
                self.drop_after = None
                break
        writer.close()
        if not self.script:                      # the app has closed: nothing answers on its port any more
            self.server.close()

    async def __aenter__(self):
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        hub.STREAMLABS_PORT = self.server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *problem):
        self.server.close()


@pytest.fixture
def quick(monkeypatch):
    monkeypatch.setattr(hub, "STREAMLABS_POLL", 0.05)
    monkeypatch.setattr(hub, "STREAMLABS_RETRY", 0.02)
    monkeypatch.setattr(hub, "STREAMLABS_GONE", 0.25)
    monkeypatch.setattr(hub, "STREAMLABS_PORT", hub.STREAMLABS_PORT)
    hub.streaming.clear()
    yield
    hub.streaming.clear()


def test_follows_streamlabs_through_its_states(home, quick):
    home({})

    async def test():
        async with FakeStreamlabs(["offline", "starting", "live", "reconnecting", "ending", "offline", "offline"]) as fake:
            await asyncio.wait_for(hub.streamlabs_link(), 10)
            return fake.seen
    # what the hub thought just before each question: on air from "live" until "offline", "reconnecting" and "ending" included
    assert asyncio.run(test()) == [False, False, False, True, True, True, False]


def test_a_streamlabs_that_says_nothing_or_is_busy_changes_nothing(home, quick):
    home({})

    async def test():
        async with FakeStreamlabs(["live", None, "busy", "live", "offline", "offline"]) as fake:
            await asyncio.wait_for(hub.streamlabs_link(), 10)
            return fake.seen
    assert asyncio.run(test()) == [False, True, True, True, True, False]


def test_streamlabs_closing_ends_the_stream_and_the_hub(home, quick):
    home({"broadcaster": "streamlabs"})

    async def test():
        async with FakeStreamlabs(["live", "live"]):
            await asyncio.wait_for(hub.follow_app(), 10)
        return hub.streaming.is_set()
    assert asyncio.run(test()) is False


def test_a_short_gap_is_not_streamlabs_closing(home, quick):
    """Changing Streamlabs' Remote Control settings drops every connection for a moment."""
    home({})

    async def test():
        async with FakeStreamlabs(["live", "live", "offline", "offline"], drop_after=2) as fake:
            await asyncio.wait_for(hub.streamlabs_link(), 10)
            return fake.connections, fake.seen
    connections, seen = asyncio.run(test())
    assert connections == 2 and seen == [False, True, True, False]


def test_waits_as_long_as_it_takes_for_streamlabs_to_open(home, quick):
    home({})

    async def test():
        holder = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
        port = holder.sockets[0].getsockname()[1]
        holder.close()
        await holder.wait_closed()
        hub.STREAMLABS_PORT = port
        link = asyncio.create_task(hub.streamlabs_link())
        await asyncio.sleep(hub.STREAMLABS_GONE * 2)         # longer than a gap may be, before it was ever open
        assert not link.done()
        fake = FakeStreamlabs(["live", "offline", "offline"])
        fake.server = await asyncio.start_server(fake.handle, "127.0.0.1", port)
        await asyncio.wait_for(link, 10)
        fake.server.close()
        return fake.seen
    assert asyncio.run(test()) == [False, True, False]


@pytest.mark.parametrize("config, argv, running, expected", [
    ({}, ["--obs-pid", "1"], True, "obs"),             # OBS started this hub: OBS, whatever else is open
    ({}, ["--obs-stdin"], True, "obs"),
    ({}, [], True, "streamlabs"),                      # started by hand with Streamlabs open
    ({}, [], False, "obs"),                            # started by hand with nothing open: as it always was
    ({"broadcaster": "obs"}, [], True, "obs"),         # config.json decides
    ({"broadcaster": "streamlabs"}, ["--obs-pid", "1"], False, "streamlabs"),
    ({"broadcaster": "xsplit"}, [], False, "obs"),     # a name it doesn't know is "auto"
    ({"broadcaster": " Streamlabs "}, [], False, "streamlabs"),
])
def test_which_app_is_followed(home, monkeypatch, quick, config, argv, running, expected):
    home(config, *argv)
    followed = []

    async def link(name):
        followed.append(name)

    async def answers():
        return running
    monkeypatch.setattr(hub, "obs_link", lambda: link("obs"))
    monkeypatch.setattr(hub, "streamlabs_link", lambda: link("streamlabs"))
    monkeypatch.setattr(hub, "streamlabs_answers", answers)
    asyncio.run(hub.follow_app())
    assert followed == [expected] and hub.state["app"] == expected


def test_something_unexpected_goes_up_to_keep_running(home, monkeypatch, quick):
    home({"broadcaster": "streamlabs"})

    async def broken():
        raise RuntimeError("boom")
    monkeypatch.setattr(hub, "streamlabs_link", broken)
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(hub.follow_app())


async def serving(test):
    server = await asyncio.start_server(hub.serve, "127.0.0.1", 0)
    hub.PORT = server.sockets[0].getsockname()[1]
    async with server:
        return await test()


async def get(path, extra=None):
    reader, writer = await asyncio.open_connection("127.0.0.1", hub.PORT)
    head = {"Host": "127.0.0.1:%d" % hub.PORT, **(extra or {})}
    writer.write(("GET %s HTTP/1.1\r\n" % path + "".join("%s: %s\r\n" % kv for kv in head.items()) + "\r\n").encode())
    await writer.drain()
    data = await asyncio.wait_for(reader.read(), 5)
    writer.close()
    status, _, rest = data.partition(b"\r\n")
    return int(status.split()[1]), rest.partition(b"\r\n\r\n")[2]


def test_start_and_end_stream_when_following_no_app(home, quick):
    home({"broadcaster": "manual"})

    async def test():
        following = asyncio.create_task(hub.follow_app())
        await asyncio.sleep(0.05)
        out = [hub.streaming.is_set()]
        for go in ("start", "start", "nonsense", "end"):
            status, body = await get("/stream?go=" + go)
            assert status == 200
            out.append((json.loads(body)["ok"], hub.streaming.is_set()))
        who = json.loads((await get("/whoami"))[1])
        assert who["app"] == "manual"
        assert json.loads((await get("/leave"))[1]) == {"ok": True}
        await asyncio.wait_for(following, 5)
        return out
    assert asyncio.run(serving(test)) == [False, (True, True), (True, True), (False, True), (True, False)]


def test_leaving_while_live_ends_the_stream(home, quick):
    home({"broadcaster": "manual"})

    async def test():
        following = asyncio.create_task(hub.follow_app())
        await asyncio.sleep(0.05)
        await get("/stream?go=start")
        assert hub.streaming.is_set()
        await get("/leave")
        await asyncio.wait_for(following, 5)
        return hub.streaming.is_set()
    assert asyncio.run(serving(test)) is False


def test_start_stream_is_refused_when_an_app_decides(home, quick):
    home({})

    async def test():
        for app in ("obs", "streamlabs", None):
            hub.state["app"] = app
            answer = json.loads((await get("/stream?go=start"))[1])
            assert answer["ok"] is False and "knows by itself" in answer["why"] and not hub.streaming.is_set()
        hub.state["leave"] = None
        assert json.loads((await get("/leave"))[1]) == {"ok": False}          # with OBS, CrossChat closes with OBS
    asyncio.run(serving(test))


def test_another_website_cannot_start_the_stream_or_close_crosschat(home, quick):
    home({})

    async def test():
        hub.state["app"] = "manual"
        hub.state["leave"] = asyncio.Event()
        for path in ("/stream?go=start", "/leave"):
            assert (await get(path, {"Origin": "https://example.com"}))[0] == 403
            assert (await get(path, {"Sec-Fetch-Site": "cross-site"}))[0] == 403
        assert not hub.streaming.is_set() and not hub.state["leave"].is_set()
    asyncio.run(serving(test))


def test_a_paired_device_cannot_start_the_stream_or_close_crosschat():
    head = {"host": "192.168.1.20:4467"}
    assert hub.remote_refused("GET", head, "/stream", {"name": "phone"}) == "not available on a paired device"
    assert hub.remote_refused("GET", head, "/leave", {"name": "phone"}) == "not available on a paired device"


@pytest.mark.parametrize("value, ok", [("auto", True), ("obs", True), ("streamlabs", True), ("manual", True), ("xsplit", False), ("", False), (7, False)])
def test_the_streaming_app_setting(tmp_path, value, ok):
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    answer, _ = settings_ui.save(str(path), {"broadcaster": value}, {"broadcaster": "streamlabs" if value == "auto" else "auto"}, hub.channel)
    assert answer["ok"] is ok
    if ok:
        assert json.loads(path.read_text(encoding="utf-8"))["broadcaster"] == value
        assert answer["restart"] == ["broadcaster"]


def test_what_to_restart_depends_on_the_app(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")

    def said(fields, config):
        return settings_ui.save(str(path), fields, config, hub.channel)[0]["why"]
    assert "Close CrossChat and open it again to apply: Streaming app" in said({"broadcaster": "manual"}, {"broadcaster": "auto"})
    assert "Restart OBS to apply: Streaming app" in said({"broadcaster": "obs"}, {"broadcaster": "manual"})
    assert "Close CrossChat and open it again to apply: Twitch" in said({"twitch": "ann"}, {"broadcaster": "streamlabs"})


def test_the_hub_and_the_pages_agree_on_the_theme_limit():
    with open(hub.os.path.join(hub.WEB, "theme.js"), encoding="utf-8") as f:
        kilobytes = re.search(r"THEME_MOST = (\d+) \* 1024", f.read()).group(1)
    assert int(kilobytes) * 1024 == hub.THEME_MOST
    assert hub.THEME_MOST + 1024 < hub.BODY_LIMIT         # a whole theme fits in one request
