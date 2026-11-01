"""The macOS (beta) helpers in hub/macos.py. The path handling runs everywhere; the rest needs a Mac."""
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
