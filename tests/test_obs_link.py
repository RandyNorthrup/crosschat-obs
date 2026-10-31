"""The hub against a stand-in for obs-websocket 5: authentication, stream start and stop, a wrong password."""
import asyncio
import json

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
