import json

import hub
import pytest


@pytest.mark.parametrize(("given", "platform", "used"), [
    ("RandomStreamer", "twitch", "randomstreamer"),
    ("https://www.twitch.tv/Some_Name/videos", "twitch", "some_name"),
    ("@some_name", "twitch", "some_name"),
    ("name with spaces", "twitch", ""),
    ("https://www.youtube.com/@LofiGirl/live", "youtube", "@LofiGirl"),
    ("@LofiGirl", "youtube", "@LofiGirl"),
    ("LofiGirl", "youtube", "@LofiGirl"),
    ("https://youtube.com/channel/UCSJ4gkVC6NrvII8umztf0Ow", "youtube", "UCSJ4gkVC6NrvII8umztf0Ow"),
    ("x", "youtube", ""),
    ("kick.com/some-slug", "kick", "some-slug"),
    ("", "kick", ""),
])
def test_channels_are_cleaned_up(given, platform, used):
    assert hub.channel(given, platform) == used


def test_missing_config_uses_defaults(home):
    home()
    assert hub.PORT == 4466
    assert hub.X == {}                                  # X is off until switched on
    assert hub.CFG["overlay"] == {"platforms": "all", "theme": "classic"}
    assert hub.CFG["obs"]["port"] == 0


def test_config_is_laid_over_the_defaults(home):
    home({"twitch": "https://twitch.tv/SomeOne", "x": {"enabled": True, "title": "Hello"}, "extra": 1})
    assert hub.TWITCH == "someone"
    assert hub.X["title"] == "Hello"
    assert hub.X["end_with_obs"] is True                # untouched defaults inside a section stay
    assert hub.CFG["extra"] == 1


def test_broken_config_falls_back_to_defaults(home):
    home("{ not json")
    assert hub.PORT == 4466 and hub.TWITCH == ""


def test_command_line_wins(home):
    home({"twitch": "a", "port": 5000}, "--twitch", "b", "--port", "5001", "--kick", "slug:42")
    assert (hub.TWITCH, hub.PORT, hub.KICK, hub.KICK_ROOM) == ("b", 5001, "slug", 42)


def test_x_title_from_file(home, tmp_path):
    (tmp_path / "now.txt").write_text("Building a parser\nsecond line", encoding="utf-8")
    home({"x": {"enabled": True, "title": "Fallback", "title_file": str(tmp_path / "now.txt"), "title_prefix": "Live: "}})
    assert hub.x_title() == "Live: Building a parser"
    (tmp_path / "now.txt").write_text("", encoding="utf-8")
    assert hub.x_title() == "Fallback"


def test_obs_settings_come_from_obs_unless_set(home, tmp_path):
    folder = tmp_path / "obs-studio" / "plugin_config" / "obs-websocket"
    folder.mkdir(parents=True)
    (folder / "config.json").write_text(json.dumps({"server_port": 4999, "server_password": "secret", "server_enabled": True}))
    home(None, "--obs-config", str(tmp_path / "obs-studio"))
    assert hub.obs_settings() == {"host": "127.0.0.1", "port": 4999, "password": "secret", "enabled": True}
    home({"obs": {"port": 4000, "password": "mine"}}, "--obs-config", str(tmp_path / "obs-studio"))
    assert hub.obs_settings()["port"] == 4000 and hub.obs_settings()["password"] == "mine"


def test_window_boxes(home):
    home()
    assert hub.box({"x": 1, "y": 2, "width": 300, "height": 400}, "chat") == (1, 2, 300, 400)
    x, y, width, height = hub.box("auto", "chat")
    left, top, right, bottom = hub.work_area()
    assert x + width == right and y == top and height == bottom - top    # X off: the chat takes the whole strip
