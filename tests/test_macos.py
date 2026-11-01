"""The macOS (beta) helpers in hub/macos.py. The path handling and the rules run everywhere; the rest needs a Mac."""
import asyncio
import os
import sys

import hub
import macos
import pytest

mac_only = pytest.mark.skipif(sys.platform != "darwin", reason="needs macOS")


def test_a_browser_is_named_by_its_app_folder(tmp_path):
    assert macos.bundle("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome") == "/Applications/Google Chrome.app"
    assert macos.bundle("/Applications/Microsoft Edge.app/") == "/Applications/Microsoft Edge.app"
    mine = tmp_path / "My Browser.app"
    mine.mkdir()
    assert macos.browser(str(mine)) == str(mine)
    assert macos.browser(str(tmp_path / "Missing.app")) is None
    assert macos.browser(str(tmp_path)) is None                  # a folder, but not an app


def test_no_browser_means_no_windows():
    assert macos.windows(None, "CrossChat") == []
    macos.place(None, 0, 0, 1, 1)                                # nothing to move or close: nothing happens
    macos.close(None)


def test_a_refusal_is_not_asked_again_for_a_minute(monkeypatch):
    asked = []
    monkeypatch.setattr(macos, "_refused", {"until": 0.0})
    monkeypatch.setattr(macos, "_script", lambda *a, **k: asked.append(a) or None)     # macOS says no, or nobody answers
    assert macos.windows("/Applications/Google Chrome.app", "CrossChat") is None
    assert macos.windows("/Applications/Google Chrome.app", "CrossChat") is None
    assert len(asked) == 1                                       # the second time CrossChat didn't even ask


def test_a_window_opens_even_when_crosschat_may_not_manage_it(monkeypatch):
    answers = iter([[], None])                                   # before: no windows; after: macOS refuses
    launched = []
    monkeypatch.setattr(macos, "windows", lambda app, prefix=None: next(answers))
    monkeypatch.setattr(macos.subprocess, "run", lambda command, **k: launched.append(command))
    handle = asyncio.run(macos.open_app("/Applications/Google Chrome.app", "http://127.0.0.1:4466/", (10, 20, 300, 400)))
    assert handle is None
    assert launched == [["open", "-n", "-a", "/Applications/Google Chrome.app", "--args", "--app=http://127.0.0.1:4466/",
                         "--window-position=10,20", "--window-size=300,400"]]


@mac_only
def test_the_hub_does_its_windows_jobs_the_mac_way(home):
    home(None)
    assert hub.MAC
    left, top, right, bottom = hub.work_area()
    assert right > left and bottom > top
    assert hub.obs_open(os.getpid()) and not hub.obs_open(2 ** 22 + 12345)
    assert hub.network_category("192.168.1.20") == ""
    assert isinstance(hub.browser_windows("CrossChat"), list)


@mac_only
def test_obs_settings_default_to_obs_own_folder_on_a_mac(home, tmp_path, monkeypatch):
    assert macos.OBS_SETTINGS == os.path.expanduser("~/Library/Application Support/obs-studio")
    folder = tmp_path / "obs-studio" / "plugin_config" / "obs-websocket"
    folder.mkdir(parents=True)
    (folder / "config.json").write_text('{"server_port": 4999, "server_password": "pw", "server_enabled": true}')
    monkeypatch.setattr(macos, "OBS_SETTINGS", str(tmp_path / "obs-studio"))
    home(None)
    assert hub.obs_settings() == {"host": "127.0.0.1", "port": 4999, "password": "pw", "enabled": True}
