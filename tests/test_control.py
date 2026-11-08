"""hub/control.py, which the OBS script's buttons and the shortcuts run: it starts the hub when it has to, and waits until
the hub really answers."""
import io
import urllib.error

import control
import pytest


class Clock:
    """Stands in for the time module, so the waiting takes no time at all."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Machine:
    """This PC as control.py sees it: a hub that starts when asked and answers `up_after` seconds later."""

    def __init__(self, monkeypatch, up_after):
        self.clock, self.up_after, self.up_at = Clock(), up_after, None
        self.asked, self.started, self.shown = [], [], []
        monkeypatch.setattr(control, "time", self.clock)
        monkeypatch.setattr(control.urllib.request, "urlopen", self.urlopen)
        monkeypatch.setattr(control.subprocess, "Popen", self.popen)
        monkeypatch.setattr(control, "show", lambda address: self.shown.append((address, self.answering())))
        monkeypatch.setattr(control, "port", lambda: 4466)

    def answering(self):
        return self.up_at is not None and self.clock.now >= self.up_at

    def popen(self, command, **kw):
        self.started.append((command, kw))
        self.up_at = self.clock.now + self.up_after

    def urlopen(self, address, timeout=None):
        self.asked.append(address)
        if not self.answering():
            raise urllib.error.URLError("connection refused")
        return io.BytesIO(b'{"version": "1.9.0"}')


def test_open_chat_waits_for_a_hub_that_starts_slowly(monkeypatch):
    machine = Machine(monkeypatch, up_after=8)
    assert control.main("show") == 0
    assert len(machine.started) == 1 and machine.asked[-1] == "http://127.0.0.1:4466/show"


def test_open_chat_gives_up_on_a_hub_that_never_answers(monkeypatch):
    machine = Machine(monkeypatch, up_after=10 ** 6)
    assert control.main("show") == 1
    assert machine.clock.now <= control.HUB_WAIT + 2 * control.HUB_POLL


def test_a_hub_already_running_is_not_started_again(monkeypatch):
    machine = Machine(monkeypatch, up_after=0)
    machine.up_at = 0.0
    assert control.main("show") == 0 and machine.started == []


def test_the_demo_page_opens_only_once_the_demo_answers(monkeypatch):
    machine = Machine(monkeypatch, up_after=8)
    assert control.main("demo") == 0
    assert machine.shown == [("http://127.0.0.1:%d/" % control.DEMO_PORT, True)]
    assert machine.started[0][0][-5:] == ["--demo", "--quiet", "--no-window", "--port", str(control.DEMO_PORT)]


def test_a_demo_already_running_is_not_started_again(monkeypatch):
    machine = Machine(monkeypatch, up_after=0)
    machine.up_at = 0.0
    assert control.main("demo") == 0 and machine.started == []


def test_the_hub_is_started_the_same_way_every_time(monkeypatch):
    first, second = Machine(monkeypatch, up_after=1), Machine(monkeypatch, up_after=1)
    monkeypatch.setattr(control.subprocess, "Popen", first.popen)
    monkeypatch.setattr(control.urllib.request, "urlopen", first.urlopen)
    monkeypatch.setattr(control, "time", first.clock)
    control.main("show")
    monkeypatch.setattr(control.subprocess, "Popen", second.popen)
    monkeypatch.setattr(control.urllib.request, "urlopen", second.urlopen)
    monkeypatch.setattr(control, "time", second.clock)
    control.main("demo")
    (show, show_kw), (demo, demo_kw) = first.started[0], second.started[0]
    assert show_kw == demo_kw and show == demo[:len(show)]


@pytest.mark.parametrize("answer", [b"<html>another program</html>", b"[1, 2]", b"5"])
def test_only_a_crosschat_hub_counts_as_answering(monkeypatch, answer):
    monkeypatch.setattr(control.urllib.request, "urlopen", lambda address, timeout=None: io.BytesIO(answer))
    assert control.answers("http://127.0.0.1:4466") is False
