"""The demo (hub.py --demo): a made-up live stream on every platform, with nothing leaving this PC."""
import asyncio

import hub
import pytest

real_sleep = asyncio.sleep


@pytest.fixture
def demo_rounds(home, monkeypatch):
    """Runs demo_stream for `rounds` rounds of made-up chat, without the waits between them."""
    home({}, "--demo")
    assert hub.DEMO
    hub.health.clear()

    def play(rounds):
        waited = [0]

        async def sleep(seconds):
            waited[0] += 1
            if waited[0] > rounds:
                raise asyncio.CancelledError
            await real_sleep(0)
        monkeypatch.setattr(hub.asyncio, "sleep", sleep)
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(hub.demo_stream())
    return play


def test_the_demos_platforms_are_exactly_the_hubs_platforms():
    assert set(hub.DEMO_PEOPLE) == set(hub.NAMES) and len(hub.NAMES) == 8
    assert set(hub.DEMO_PREFIX) == set(hub.NAMES) and set(hub.DEMO_WEIGHTS) == set(hub.NAMES)
    assert all(hub.DEMO_PEOPLE.values())


def test_every_platform_is_live_and_counted_in_the_demo(demo_rounds):
    demo_rounds(1)
    assert set(hub.status) == set(hub.NAMES) and set(hub.status.values()) == {"on"}
    assert set(hub.viewers) == set(hub.NAMES) and all(hub.viewers.values())
    assert set(hub.health) == set(hub.NAMES)


def test_every_platform_talks_in_the_demo(demo_rounds):
    demo_rounds(400)
    assert {m["p"] for m in hub.messages if m["kind"] == "chat"} == set(hub.NAMES)


def test_replies_and_moderation_in_the_demo_never_leave_this_pc(demo_rounds, monkeypatch):
    demo_rounds(400)
    done = []
    monkeypatch.setattr(hub, "by_executor", lambda *a, **k: done.append(a))        # (the way out to the real platforms)

    async def sleep(seconds):
        await real_sleep(0)
    monkeypatch.setattr(hub.asyncio, "sleep", sleep)
    window = asyncio.Queue()
    hub.clients.add(window)
    asyncio.run(hub.run_send({"id": "j1", "kind": "send", "to": list(hub.NAMES), "text": "hello", "reply": None, "dry": False}))
    sent = next(e for e in (window.get_nowait() for _ in range(window.qsize())) if e["type"] == "sent")
    assert set(sent["answer"]) == set(hub.NAMES) and all(a["ok"] for a in sent["answer"].values())
    said = next(m for m in hub.messages if m["p"] == "rumble" and m.get("mid"))
    asyncio.run(hub.run_mod({"id": "j2", "kind": "mod", "p": "rumble", "action": "delete", "message_id": said["mid"], "user_id": said.get("uid", "")}))
    assert done == []                                                  # nothing was handed to the extension
