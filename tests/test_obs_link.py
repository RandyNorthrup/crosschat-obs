"""The hub against a stand-in for obs-websocket 5: authentication, stream start and stop, a wrong password."""
import asyncio
import json
import os

import hub
from websockets.asyncio.server import serve

PASSWORD = "right"


def fake_obs(script, password=PASSWORD):
    """An obs-websocket stand-in. `script(ws, request)` sends events; `request(kind)` waits for the hub to ask for it."""
    async def handler(ws):
        await ws.send(json.dumps({"op": 0, "d": {"obsStudioVersion": "33.0.1", "obsWebSocketVersion": "5.7.6", "rpcVersion": 1,
                                                 "authentication": {"challenge": "c", "salt": "s"}}}))
        ident = json.loads(await ws.recv())["d"]
        if ident.get("authentication") != hub.answer({"challenge": "c", "salt": "s"}, password):
            await ws.close(4009, "Authentication failed.")
            return
        await ws.send(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}))
        asked = asyncio.Queue()

        async def read():
            async for raw in ws:
                await asked.put(json.loads(raw)["d"])
        reading = asyncio.create_task(read())

        async def request(kind, data):
            while True:
                d = await asyncio.wait_for(asked.get(), 5)
                if d["requestType"] == kind:
                    await ws.send(json.dumps({"op": 7, "d": {"requestType": kind, "requestId": d["requestId"],
                                                             "requestStatus": {"result": True, "code": 100}, "responseData": data}}))
                    return
        await script(ws, request)
        reading.cancel()
        await ws.close()
    return serve(handler, "127.0.0.1", 0)


def event(ws, state):
    return ws.send(json.dumps({"op": 5, "d": {"eventType": "StreamStateChanged", "eventIntent": 64,
                                              "eventData": {"outputActive": state.endswith("STARTED"), "outputState": state}}}))


def test_follows_the_stream(home):
    seen = []

    async def script(ws, request):
        await request("GetStreamStatus", {"outputActive": False})
        await event(ws, "OBS_WEBSOCKET_OUTPUT_STARTED")
        await request("GetStreamServiceSettings", {"streamServiceType": "rtmp_custom",
                                                   "streamServiceSettings": {"server": "rtmp://127.0.0.1/live"}})
        await asyncio.sleep(0.2)
        seen.append((hub.streaming.is_set(), hub.state["local"]))
        await event(ws, "OBS_WEBSOCKET_OUTPUT_STOPPED")
        await asyncio.sleep(0.2)
        seen.append((hub.streaming.is_set(), hub.state["local"]))

    async def test():
        async with fake_obs(script) as server:
            home({"obs": {"port": server.sockets[0].getsockname()[1], "password": PASSWORD}})
            hub.streaming.clear()
            await asyncio.wait_for(hub.obs_link(), 10)
    asyncio.run(test())
    assert seen == [(True, True), (False, True)]          # live, to this PC only (a test); then off air


def test_a_public_stream_is_not_a_test(home):
    seen = []

    async def script(ws, request):
        await request("GetStreamStatus", {"outputActive": True})        # already live when the hub connects
        await request("GetStreamServiceSettings", {"streamServiceSettings": {"server": "rtmp://live.twitch.tv/app"}})
        await asyncio.sleep(0.2)
        seen.append((hub.streaming.is_set(), hub.state["local"]))

    async def test():
        async with fake_obs(script) as server:
            home({"obs": {"port": server.sockets[0].getsockname()[1], "password": PASSWORD}})
            hub.streaming.clear()
            await asyncio.wait_for(hub.obs_link(), 10)
    asyncio.run(test())
    assert seen == [(True, False)]


def test_with_obs_stdin_the_hub_stays_until_its_input_ends(home, monkeypatch):
    """OBS from Flathub: no process id to watch, so the hub follows OBS (reconnecting when the connection drops) until
    the pipe OBS holds is closed, as it is when OBS ends."""
    reader, writer = os.pipe()
    real_watch = hub.watch_stdin
    monkeypatch.setattr(hub, "watch_stdin", lambda fd: real_watch(reader))
    connections = []

    async def script(ws, request):
        connections.append(1)
        await request("GetStreamStatus", {"outputActive": False})
        if len(connections) == 2:                  # the second time: OBS ends
            os.close(writer)
            await asyncio.sleep(10)                # the hub hangs up by itself

    async def test():
        async with fake_obs(script) as server:
            home({"obs": {"port": server.sockets[0].getsockname()[1], "password": PASSWORD}}, "--obs-stdin")
            await asyncio.wait_for(hub.obs_link(), 20)
    try:
        asyncio.run(test())
    finally:
        os.close(reader)
    assert len(connections) == 2 and hub.obs_gone.is_set()


def test_a_wrong_password_is_reported(home, monkeypatch):
    told = []
    monkeypatch.setattr(hub, "warn", told.append)
    monkeypatch.setattr(hub, "RETRY_AFTER_REFUSAL", 0)

    async def script(ws, request):
        raise AssertionError("not reached")

    async def test():
        async with fake_obs(script) as server:
            home({"obs": {"port": server.sockets[0].getsockname()[1], "password": "wrong"}})
            await asyncio.wait_for(hub.obs_link(), 10)
    asyncio.run(test())
    assert len(told) == 1 and "password" in told[0]


def test_every_refused_password_waits_before_trying_again(home, monkeypatch):
    """Not only the first: OBS closing the door on a wrong password every two seconds fills its log."""
    monkeypatch.setattr(hub, "warn", lambda text: None)
    monkeypatch.setattr(hub, "RETRY_AFTER_REFUSAL", 0.25)
    waits = []
    real_sleep = asyncio.sleep

    async def sleep(seconds):
        if seconds == 0.25:
            waits.append(seconds)
        await real_sleep(0 if seconds in (0.25, 2) else seconds)
    monkeypatch.setattr(hub.asyncio, "sleep", sleep)
    monkeypatch.setattr(hub, "obs_open", lambda pid: len(waits) < 3)

    async def script(ws, request):
        raise AssertionError("not reached")

    async def test():
        async with fake_obs(script) as server:
            home({"obs": {"port": server.sockets[0].getsockname()[1], "password": "wrong"}}, "--obs-pid", "123")
            await asyncio.wait_for(hub.obs_link(), 10)
    asyncio.run(test())
    assert len(waits) == 3
