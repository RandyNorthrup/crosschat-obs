"""CrossChat's windows (the chat window and the platform pages): the hub hands placing, moving and closing them to the
extension through the chat window that has it (window jobs in the outbox), and does it the system's way only when no
such window is connected or the extension can't. extension/windows.js has the extension's side (tests/js/windows.test.mjs);
scripts/window_e2e.py runs the whole thing with a real browser."""
import asyncio

import pytest

import hub
from test_companion import http, run, serving
from test_features_14 import events_in

REAL_OPEN_APP = hub.open_app                  # (conftest swaps it for a stand-in in every test)
TIKTOK = "https://www.tiktok.com/@someone/live"


@pytest.fixture
def system(home, monkeypatch):
    """A hub whose system's way of handling windows is a recorder: nothing real is opened, moved or closed."""
    home({"window": {"x": 10, "y": 20, "width": 400, "height": 600}})
    did = []
    monkeypatch.setattr(hub, "MAC", False)
    monkeypatch.setattr(hub, "LINUX", False)
    monkeypatch.setattr(hub, "browser_windows", lambda prefix=None: did.append(("find", prefix)) or [])
    monkeypatch.setattr(hub, "place", lambda handle, *where: did.append(("place", handle, where)))
    monkeypatch.setattr(hub, "close_window", lambda: did.append(("close chat",)))
    monkeypatch.setattr(hub, "close_handle", lambda handle: did.append(("close", handle)))
    monkeypatch.setattr(hub, "browser_exe", lambda: "/browser")

    async def os_open(exe, url, where, place_it):
        did.append(("open", url, where, place_it))
        return 55
    monkeypatch.setattr(hub, "os_open", os_open)
    return did


def extension(answer):
    """A chat window with the extension, connected as the executor: each window job lands in the list returned and is
    answered with answer(job) (None: no answer). Call inside a running loop."""
    queue, seen = asyncio.Queue(), []
    running.clear()                                                    # (the earlier tests' loops are gone)
    hub.clients.add(queue)
    hub.take_role("executor", queue)

    async def work():
        while True:
            event = await queue.get()
            if event.get("type") == "outbox" and event["job"].get("kind") == "window":
                seen.append(event["job"])
                reply = answer(event["job"])
                if reply is not None and event["job"]["id"] in hub.jobs:
                    hub.jobs[event["job"]["id"]].set_result(reply)
    running.append(asyncio.get_running_loop().create_task(work()))     # (kept, so it isn't collected mid-test)
    return seen


running = []


def jobs(seen):
    return [(j["action"], j["role"]) for j in seen]


# ---- the chat window ---------------------------------------------------------------------------------------------
def test_the_extension_moves_the_open_chat_window(system):
    async def test():
        seen = extension(lambda job: {"ok": True, "window": 7})
        await hub.show_window()
        return seen
    seen = run(test())
    assert jobs(seen) == [("place", "chat")] and seen[0]["box"] == [10, 20, 400, 600]
    assert system == []                                                # the system's way wasn't needed


def test_when_the_extension_cannot_move_it_the_system_does(system, monkeypatch):
    monkeypatch.setattr(hub, "browser_windows", lambda prefix=None: [7])

    async def test():
        seen = extension(lambda job: {"ok": False, "why": "Invalid value for bounds."})
        await hub.show_window()
        return seen
    assert jobs(run(test())) == [("place", "chat")]
    assert system == [("place", 7, (10, 20, 400, 600))]


def test_when_the_extensions_browser_has_no_chat_window_one_opens(system, no_windows, monkeypatch):
    """The extension sees every window of its browser, so its "none" is believed: a chat window opens even where the
    system can't see the browser's windows (Wayland) and a chat page in a tab is connected."""
    monkeypatch.setattr(hub, "LINUX", True)
    monkeypatch.setattr(hub, "linux", type("NoX", (), {"windows": staticmethod(lambda app, prefix=None: None)}), raising=False)
    hub.roles["speaker"].append(object())                              # the chat, open in a tab

    async def test():
        extension(lambda job: {"ok": False, "why": "no chat window is open", "none": True})
        await hub.show_window()
    run(test())
    assert no_windows == ["http://127.0.0.1:%d/" % hub.PORT] and system == []


def test_without_the_extension_the_chat_window_opens_and_is_placed_the_system_way(system, no_windows):
    run(hub.show_window())
    assert system == [("find", hub.TITLE)] and no_windows == ["http://127.0.0.1:%d/" % hub.PORT]
    assert hub.state["chat_opened"][0] == (10, 20, 400, 600)


def test_a_chat_window_crosschat_just_opened_is_placed_by_the_extension_once_it_connects(system, monkeypatch):
    """A running browser opens a new window where it likes (it takes --window-position only when it starts with it):
    the chat window CrossChat opened is put in its place as soon as it connects with the extension, through the real
    /events route."""
    async def test(port):
        await hub.show_window()                                       # nothing open: one opens (no extension yet)
        status, _, payload = await http(port, "GET", "/events?executor=1", read=1 << 20)
        return status, [e for e in events_in(payload) if e["type"] == "outbox"]
    status, outbox = run(serving(test))
    assert status == 200 and len(outbox) == 1
    job = outbox[0]["job"]
    assert (job["kind"], job["action"], job["role"], job["box"]) == ("window", "place", "chat", [10, 20, 400, 600])
    assert "chat_opened" not in hub.state                             # once: a reload of that window isn't moved again


def test_a_window_opened_long_ago_is_not_moved_when_it_connects(system, monkeypatch):
    hub.state["chat_opened"] = ((1, 2, 300, 400), 0.0)                 # (the person may have moved it since)

    async def test():
        seen = extension(lambda job: {"ok": True})
        await hub.chat_connected()
        return seen
    assert run(test()) == []


# ---- the platform pages ------------------------------------------------------------------------------------------
def test_a_page_is_found_and_placed_by_the_extension(system, monkeypatch):
    monkeypatch.setattr(hub, "open_app", REAL_OPEN_APP)

    def answer(job):
        return {"ok": True, "windows": [1, 2]} if job["action"] == "list" else {"ok": True, "window": 9}

    async def test():
        seen = extension(answer)
        await hub.open_page("tiktok", TIKTOK, (5, 6, 300, 200))
        return seen
    seen = run(test())
    assert jobs(seen) == [("list", ""), ("place", "tiktok")]
    place = seen[1]
    assert place["url"] == TIKTOK and place["known"] == [1, 2] and place["box"] == [5, 6, 300, 200] and place["wait"] == hub.WINDOW_WAIT
    assert system == [("open", TIKTOK, (5, 6, 300, 200), False)]       # launched, found, not placed the system's way
    assert hub.pages["tiktok"] == {"url": TIKTOK, "id": 9, "handle": 55}


def test_a_page_the_extension_did_not_find_is_placed_the_system_way(system, monkeypatch):
    monkeypatch.setattr(hub, "open_app", REAL_OPEN_APP)

    def answer(job):
        return {"ok": True, "windows": []} if job["action"] == "list" else {"ok": False, "why": "the window is not open"}

    async def test():
        extension(answer)
        await hub.open_page("tiktok", TIKTOK, (5, 6, 300, 200))
    run(test())
    assert system == [("open", TIKTOK, (5, 6, 300, 200), False), ("place", 55, (5, 6, 300, 200))]
    assert hub.pages["tiktok"] == {"url": TIKTOK, "id": None, "handle": 55}


def test_once_the_extension_placed_a_page_the_system_gets_only_a_moment_to_find_it(system, monkeypatch):
    """Where the system can't see the browser's windows, its search would hold up the next window for 30 s."""
    monkeypatch.setattr(hub, "open_app", REAL_OPEN_APP)
    monkeypatch.setattr(hub, "HANDLE_WAIT", 0.2)

    async def os_open(exe, url, where, place_it):
        await asyncio.sleep(60)                                        # never finds it

    monkeypatch.setattr(hub, "os_open", os_open)

    def answer(job):
        return {"ok": True, "windows": []} if job["action"] == "list" else {"ok": True, "window": 9}

    async def test():
        extension(answer)
        await asyncio.wait_for(hub.open_page("tiktok", TIKTOK, (5, 6, 300, 200)), 5)
    run(test())
    assert hub.pages["tiktok"] == {"url": TIKTOK, "id": 9, "handle": None}


def test_without_the_extension_a_page_opens_the_system_way(system, monkeypatch):
    monkeypatch.setattr(hub, "open_app", REAL_OPEN_APP)
    run(hub.open_page("tiktok", TIKTOK, (5, 6, 300, 200)))
    assert system == [("open", TIKTOK, (5, 6, 300, 200), True)]
    assert hub.pages["tiktok"]["handle"] == 55


def test_windows_open_one_at_a_time(system, monkeypatch):
    """The system's way knows a new window by its not having been there before: two windows opening at once could be
    taken for each other (TikTok, Facebook and Instagram open together when the stream starts)."""
    monkeypatch.setattr(hub, "open_app", REAL_OPEN_APP)
    busy = []

    async def os_open(exe, url, where, place_it):
        busy.append(url)
        assert len(busy) == 1, "two windows opening at once"
        await asyncio.sleep(0.05)
        busy.remove(url)
        return 1

    monkeypatch.setattr(hub, "os_open", os_open)

    async def test():
        await asyncio.gather(*(hub.open_page(role, url, (0, 0, 100, 100)) for role, url in (
            ("tiktok", TIKTOK), ("facebook", "https://www.facebook.com/live/producer"), ("instagram", "https://www.instagram.com/"))))
    run(test())
    assert set(hub.pages) == {"tiktok", "facebook", "instagram"}


# ---- closing -----------------------------------------------------------------------------------------------------
def test_after_the_stream_the_pages_close_first_and_the_chat_window_last(system):
    hub.pages.update({"x": {"url": "https://studio.x.com/live#golive", "id": None, "handle": 66},
                      "tiktok": {"url": TIKTOK, "id": 9, "handle": 55}})
    hub.CFG["close_window_seconds_after_stream"] = 0

    def answer(job):
        return {"ok": False, "why": "the window is not open"} if job["role"] == "x" else {"ok": True}

    async def test():
        seen = extension(answer)
        hub.streaming.set()
        await hub.stream_stopped()
        await hub.closing
        return seen
    seen = run(test())
    assert jobs(seen) == [("close", "x"), ("close", "tiktok"), ("close", "chat")]
    assert seen[1]["window"] == 9 and seen[1]["url"] == TIKTOK and seen[0]["window"] == 0
    assert system == [("close", 66)]                                    # only X's, which the extension couldn't close
    assert hub.pages == {}


def test_without_the_extension_everything_closes_the_system_way(system):
    hub.pages.update({"tiktok": {"url": TIKTOK, "id": 9, "handle": 55}})
    run(hub.close_windows())
    assert system == [("close", 55), ("close chat",)]


def test_when_obs_closes_its_x_page_and_the_chat_window_close(system, monkeypatch):
    hub.pages.update({"x": {"url": "https://studio.x.com/live", "id": 3, "handle": 66}})

    async def test():
        seen = extension(lambda job: {"ok": True})
        await hub.obs_link()                                          # (no OBS to follow: it gives up at once)
        return seen
    monkeypatch.setattr(hub, "obs_settings", lambda: {"host": "127.0.0.1", "port": 1, "password": "", "enabled": True})
    monkeypatch.setattr(hub, "connect", lambda *a, **k: (_ for _ in ()).throw(OSError("no OBS")))
    monkeypatch.setattr(hub, "warn", lambda text: None)

    async def no_wait(seconds):
        return None
    monkeypatch.setattr(hub.asyncio, "sleep", no_wait)
    assert jobs(run(test())) == [("close", "x"), ("close", "chat")]
    assert system == []


def test_the_hub_leaves_when_obs_closes_even_with_a_chat_page_still_open(home, monkeypatch):
    """A chat page's live feed never ends by itself; the hub doesn't wait for it once OBS has closed (on Python 3.12.1
    and newer, leaving "async with server" did)."""
    home({"emotes": {"bttv": False, "ffz": False, "7tv": False}, "remote": {"enabled": False}})
    connected = []

    async def obs_link():                         # OBS: here until a chat page is connected, then it closes
        while not connected:
            await asyncio.sleep(0.05)

    async def test():
        with __import__("socket").socket() as s:
            s.bind(("127.0.0.1", 0))
            hub.PORT = s.getsockname()[1]
        hub_run = asyncio.create_task(hub.main())
        await asyncio.sleep(0.5)
        reader, writer = await asyncio.open_connection("127.0.0.1", hub.PORT)
        writer.write(b"GET /events HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n\r\n" % hub.PORT)
        await reader.readline()                   # the feed is open
        connected.append(1)
        await asyncio.wait_for(hub_run, 10)        # the hub's main() returns, with the feed still open
        writer.close()
    monkeypatch.setattr(hub, "obs_link", obs_link)
    run(test())


def test_jobs_name_only_what_the_extension_needs(system):
    """Every window job is the same small shape; nothing from the chat or the settings rides along."""
    async def test():
        seen = extension(lambda job: {"ok": True})
        await hub.by_extension("place", "chat", where=(1, 2, 300, 400))
        return seen
    job = run(test())[0]
    assert set(job) == {"id", "kind", "action", "role", "url", "box", "window", "known", "wait"}
