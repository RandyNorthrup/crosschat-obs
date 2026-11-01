import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hub"))

import hub  # noqa: E402
import vault  # noqa: E402

vault.SERVICE = "CrossChat tests"


def keyring_answers():
    """Linux: whether a desktop keyring (Secret Service) answers here. Without one CrossChat keeps no secrets at all,
    so the tests that keep one (marked "keyring") are skipped. Windows and macOS always have theirs."""
    if not sys.platform.startswith("linux"):
        return True
    try:
        vault._keyring_read()
        return True
    except OSError:
        return False


KEYRING = keyring_answers()


def pytest_collection_modifyitems(items):
    if KEYRING:
        return
    skip = pytest.mark.skip(reason="no desktop keyring (Secret Service) answers on this Linux, so no secret can be kept")
    for item in items:
        if "keyring" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session", autouse=True)
def keychain():
    """On a Mac (and on Linux) the tests keep their key under a Keychain (keyring) name of their own, removed at the end
    (never CrossChat's)."""
    vault.SERVICE = "CrossChat tests"
    yield
    vault.forget_key()


@pytest.fixture(autouse=True)
def no_windows(monkeypatch):
    """No test ever opens a real browser window on the PC running the tests (a test that starts a live would), or
    closes one: the hub closes the chat window when OBS goes, and the person running the tests may have theirs open."""
    opened = []

    async def open_app(url, where, role=None):
        opened.append(url)
        return None
    monkeypatch.setattr(hub, "open_app", open_app)
    monkeypatch.setattr(hub, "close_window", lambda: None)
    monkeypatch.setattr(hub, "close_handle", lambda handle: None)
    return opened


@pytest.fixture
def home(tmp_path):
    """A hub configured from an empty folder of its own: no message boxes, no browser windows, themes kept in tmp."""
    def setup(config=None, *argv):
        path = tmp_path / "config.json"
        if config is not None:
            path.write_text(config if isinstance(config, str) else __import__("json").dumps(config), encoding="utf-8")
        hub.configure(["--config", str(path), "--quiet", "--no-window", *argv])
        hub.CFG["open_window_on_stream_start"] = False
        hub.messages.clear()
        hub.status.clear()
        hub.viewers.clear()
        hub.clients.clear()
        hub.local_clients.clear()
        hub.starred.clear()
        hub.jobs.clear()
        hub.pages.clear()
        for holders in hub.roles.values():
            holders.clear()
        hub.state.pop("chat_opened", None)
        hub.state.update({"youtube_video": "", "youtube_chat": None, "since": 0.0, "featured": None, "x_armed": None, "executor": None})
        hub.companion_setup()
        return tmp_path
    return setup
