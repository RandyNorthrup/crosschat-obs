"""The hub's web server: its pages, the Theme API, and who may ask it for what."""
import asyncio
import json
import time

import hub


def run(job):
    return asyncio.run(job)


async def serving(test):
    server = await asyncio.start_server(hub.serve, "127.0.0.1", 0)
    hub.PORT = server.sockets[0].getsockname()[1]
    async with server:
        return await test()


async def http(method, path, headers=None, body=b"", read=65536):
    """One raw request (so Host, Origin and the rest are exactly what a test says). Returns (status, body)."""
    status, _, body = await http_head(method, path, headers, body, read)
    return status, body


async def http_head(method, path, headers=None, body=b"", read=65536):
    """The same, returning (status, response headers, body)."""
    reader, writer = await asyncio.open_connection("127.0.0.1", hub.PORT)
    head = {"Host": "127.0.0.1:%d" % hub.PORT, "Content-Length": str(len(body)), **(headers or {})}
    writer.write(("%s %s HTTP/1.1\r\n" % (method, path) + "".join("%s: %s\r\n" % kv for kv in head.items() if kv[1] is not None)
                  + "\r\n").encode() + body)
    await writer.drain()
    data = b""
    try:
        while len(data) < read:
            chunk = await asyncio.wait_for(reader.read(read), 2)
            if not chunk:
                break
            data += chunk
    except asyncio.TimeoutError:
        pass
    writer.close()
    status, _, rest = data.partition(b"\r\n")
    head, _, payload = rest.partition(b"\r\n\r\n")
    return int(status.split()[1]) if status else 0, head.decode("latin1"), payload


def own(extra=None):
    return {"Origin": "http://127.0.0.1:%d" % hub.PORT, "Content-Type": "application/json", **(extra or {})}


def post(path, data, headers=None):
    return http("POST", path, headers or own(), json.dumps(data).encode())


def test_pages_are_served(home):
    home()

    async def test():
        for path in ("/", "/studio", "/overlay/chat", "/overlay/featured", "/overlay/viewers", "/overlay/alerts", "/web/theme.js"):
            status, body = await http("GET", path)
            assert status == 200 and body, path
        assert (await http("GET", "/overlay/nope"))[0] == 404
        assert (await http("GET", "/web/../hub.py"))[0] == 404
        assert (await http("GET", "/themes/..%2Fconfig"))[0] == 404
        assert json.loads((await http("GET", "/version"))[1]) == {"version": hub.VERSION}
    run(serving(test))


def test_only_this_pc_and_its_own_pages_may_act(home):
    home()

    async def test():
        assert (await http("GET", "/", {"Host": "evil.example"}))[0] == 403            # DNS rebinding
        assert (await http("GET", "/feature?clear=1", {"Origin": "https://evil.example"}))[0] == 403
        assert (await http("GET", "/x/go?mode=dry", {"Sec-Fetch-Site": "cross-site"}))[0] == 403
        assert (await http("GET", "/themes", {"Origin": "https://evil.example"}))[0] == 403   # not even reading
        assert (await http("GET", "/", {"Sec-Fetch-Site": "cross-site"}))[0] == 403        # nor opening the window
        assert (await http("GET", "/themes", {"Origin": "null"}))[0] == 403                # nor a sandboxed frame
        page = {"Origin": "http://localhost:%d" % hub.PORT, "Sec-Fetch-Site": "cross-site"}
        assert (await http("GET", "/themes", page))[0] == 200                              # your own overlay pages
        status, head, _ = await http_head("GET", "/")
        assert "X-Frame-Options: DENY" in head and "frame-ancestors 'none'" in head
        status, head, _ = await http_head("GET", "/studio")
        assert "X-Frame-Options: DENY" in head
        status, head, _ = await http_head("GET", "/overlay/chat")
        assert "default-src 'self'" in head and "connect-src 'self'" in head and "Access-Control-Allow-Origin" not in head
        assert (await post("/test", {"kind": "chat"}, {"Origin": "https://evil.example", "Content-Type": "application/json"}))[0] == 403
        assert (await post("/test", {"kind": "chat"}, {"Origin": "http://127.0.0.1:%d" % hub.PORT, "Content-Type": "text/plain"}))[0] == 403
        assert (await http("POST", "/test", own({"Content-Length": str(hub.BODY_LIMIT + 1)})))[0] == 413
        assert (await http("POST", "/test", own(), b"[1, 2]"))[0] == 400
        assert (await http("GET", "/feature?clear=1"))[0] == 200                         # the OBS script and shortcuts
    run(serving(test))


def test_theme_api(home):
    folder = home()

    async def test():
        listed = json.loads((await http("GET", "/themes"))[1])
        builtins = {t["name"] for t in listed["themes"] if t["builtin"]}
        assert "classic" in builtins and listed["default"] == "classic"
        assert json.loads((await post("/themes/save", {"name": "mine", "theme": {"schema": 1, "label": "Mine"}}))[1]) == {"ok": True}
        assert json.loads((folder / "themes" / "mine.json").read_text(encoding="utf-8"))["label"] == "Mine"
        assert {"name": "mine", "label": "Mine", "builtin": False} in json.loads((await http("GET", "/themes"))[1])["themes"]
        assert json.loads((await http("GET", "/themes/mine"))[1])["label"] == "Mine"
        refused = json.loads((await post("/themes/save", {"name": "classic", "theme": {}}))[1])
        assert refused["ok"] is False and "comes with CrossChat" in refused["why"]
        assert json.loads((await post("/themes/save", {"name": "Bad Name", "theme": {}}))[1])["ok"] is False
        assert json.loads((await post("/themes/save", {"name": "big", "theme": {"css": "x" * 70000}}))[1])["ok"] is False
        assert json.loads((await post("/themes/default", {"name": "mine"}))[1]) == {"ok": True}
        assert json.loads((await http("GET", "/themes"))[1])["default"] == "mine"
        assert json.loads((await post("/themes/delete", {"name": "mine"}))[1]) == {"ok": True}
        assert not (folder / "themes" / "mine.json").exists()
        assert json.loads((await http("GET", "/themes"))[1])["default"] == "classic"   # a deleted default falls back
        assert json.loads((await post("/themes/delete", {"name": "classic"}))[1])["ok"] is False
    run(serving(test))


def test_live_feed_featured_messages_and_tests(home):
    home()

    async def test():
        queue = asyncio.Queue()
        hub.clients.add(queue)
        hub.publish("twitch", "ann", "hello", mid="tw-1")
        assert (await http("GET", "/feature?id=tw-1"))[0] == 200
        events = [queue.get_nowait() for _ in range(queue.qsize())]
        assert {"type": "feature", "msg": hub.messages[-1]} in events and hub.state["featured"]["id"] == "tw-1"
        assert json.loads((await http("GET", "/feature?id=missing"))[1]) == {"ok": False}
        assert hub.state["featured"]["id"] == "tw-1"            # a message too old to find leaves the featured one alone
        await http("GET", "/feature?clear=1")
        assert hub.state["featured"] is None
        assert json.loads((await post("/test", {"kind": "alert"}))[1]) == {"ok": True}
        await asyncio.sleep(0.1)
        alert = [e for e in (queue.get_nowait() for _ in range(queue.qsize())) if e["type"] == "msg"][-1]
        assert alert["kind"] == "event" and alert["test"] is True and alert["alert"]
        assert json.loads((await post("/test", {"kind": "nope"}))[1])["ok"] is False
        status, body = await http("GET", "/events", read=50000)
        whole = body.decode().rpartition("\n\n")[0]                 # complete events only
        lines = [json.loads(line[6:]) for line in whole.split("\n") if line.startswith("data: ")]
        assert status == 200 and {e["type"] for e in lines} >= {"msg", "status", "viewers", "feature"}
    run(serving(test))


def test_custom_overlays_stay_inside_their_folder(home, tmp_path):
    mine = tmp_path / "overlays"
    (mine / "fonts").mkdir(parents=True)
    (mine / "chat.html").write_text("<html>mine</html>", encoding="utf-8")
    (mine / "fonts" / "a.woff2").write_bytes(b"font")
    (mine / "notes.exe").write_bytes(b"MZ")
    (tmp_path / "secret.txt").write_text("no", encoding="utf-8")
    home({"custom_overlays": str(mine)})

    async def test():
        # the old address sends them to their own one, which the browser keeps apart from the CrossChat window's
        status, head, _ = await http_head("GET", "/custom/chat.html?x=1")
        assert status == 302 and "Location: http://localhost:%d/custom/chat.html?x=1" % hub.PORT in head
        mine_ = {"Host": "localhost:%d" % hub.PORT}
        status, body = await http("GET", "/custom/chat.html", mine_)
        assert status == 200 and body == b"<html>mine</html>"
        assert (await http("GET", "/custom/fonts/a.woff2", {**mine_, "Sec-Fetch-Site": "same-origin"}))[0] == 200
        assert (await http("GET", "/custom/fonts/a.woff2", {**mine_, "Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}))[0] == 403
        for path in ("/", "/studio", "/logs", "/targets", "/feature?clear=1", "/show", "/x/go?mode=dry"):
            assert (await http("GET", path, mine_))[0] == 403, path                         # nothing of the CrossChat window
        assert (await http("POST", "/send", {**mine_, "Origin": "http://localhost:%d" % hub.PORT, "Content-Type": "application/json"},
                           b'{"to": ["twitch"], "text": "x"}'))[0] == 403
        assert (await http("GET", "/settings", mine_))[0] == 200
        for bad in ("/custom/notes.exe", "/custom/../secret.txt", "/custom/%2e%2e/secret.txt", "/custom/fonts/../../secret.txt",
                    "/custom/C:/Windows/win.ini", "/custom/missing.html"):
            assert (await http("GET", bad, mine_))[0] == 404, bad
    run(serving(test))
    home({})
    assert hub.custom_file("chat.html") is None                  # no folder set: nothing is served


def test_x_requests_are_used_once(home):
    home({"x": {"enabled": True, "title": "T", "source": "OBS"}})

    async def test():
        hub.state["x_armed"] = ("dry", time.time())
        first = json.loads((await http("GET", "/x/state", {"Origin": "chrome-extension://abc"}))[1])
        again = json.loads((await http("GET", "/x/state", {"Origin": "chrome-extension://abc"}))[1])
        assert (first["go"], first["title"], again["go"]) == ("dry", "T", "")
        await http("GET", "/x/feed?viewers=12&name=Ann&handle=ann&text=hi&id=abc", {"Origin": "chrome-extension://abc"})
        assert hub.status["x"] == "on" and hub.viewers["x"] == 12 and hub.messages[-1]["text"] == "hi"
        await http("GET", "/x/feed?viewers=12&name=Ann&handle=ann&text=hi&id=abc")          # the same line again: shown once
        assert sum(1 for m in hub.messages if m["p"] == "x") == 1
        await http("GET", "/x/result?ok=1&mode=end&step=done")
        assert hub.status["x"] == "off"
    run(serving(test))
