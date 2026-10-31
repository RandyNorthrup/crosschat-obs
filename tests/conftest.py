import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hub"))

import hub  # noqa: E402


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
        for holders in hub.roles.values():
            holders.clear()
        hub.state.update({"youtube_video": "", "youtube_chat": None, "since": 0.0, "featured": None, "x_armed": None, "executor": None})
        hub.companion_setup()
        return tmp_path
    return setup
