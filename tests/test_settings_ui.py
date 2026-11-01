"""Settings → Channels & options: GET /config/editable and POST /config. Only this PC's CrossChat window may read or
change them, every value is checked, config.json is replaced in one step (with a .bak), and no secret ever leaves."""
import json
import os
import re

import hub
import settings_ui
from test_companion import http, post, run, same_origin, serving

SECRETS = {"kick_client_id": "my-kick-app", "kick_client_secret": "kick-secret-value-123", "twitch_client_id": "my-twitch-app",
           "obs": {"host": "127.0.0.1", "port": 4455, "password": "obs-password-456"}, "custom_overlays": "C:\\private\\overlays"}


def paired_cookie():
    code, _ = hub.DEV.start_pairing()
    return {"Cookie": "cc_device=" + hub.DEV.pair(code, "Phone")}


def test_the_editable_settings_never_include_secrets(home):
    home({"twitch": "Some_Streamer", "x": {"enabled": True, "title": "Building live"}, "mystery": 1, **SECRETS})

    async def test(port):
        status, _, body = await http(port, "GET", "/config/editable")
        assert status == 200
        got = json.loads(body)
        assert set(got["settings"]) == set(settings_ui.FIELDS)
        assert got["settings"]["twitch"] == "Some_Streamer" and got["settings"]["x.title"] == "Building live"
        assert got["settings"]["x.enabled"] is True and got["first_run"] is False
        text = body.decode()
        for secret in ("my-kick-app", "kick-secret-value-123", "my-twitch-app", "obs-password-456", "private", "mystery"):
            assert secret not in text, secret
    run(serving(test))


def test_a_config_without_channels_is_a_first_run(home):
    home({})
    assert settings_ui.editable(hub.CFG)["first_run"] is True
    home({"kick": "someone"})
    assert settings_ui.editable(hub.CFG)["first_run"] is False


def test_other_websites_overlay_pages_and_paired_devices_cannot_read_or_change_settings(home):
    folder = home({"twitch": "mine", **SECRETS})
    before = (folder / "config.json").read_text()

    async def local(port):
        evil = {"Origin": "http://evil.example", "Sec-Fetch-Site": "cross-site"}
        assert (await http(port, "GET", "/config/editable", evil))[0] == 403
        assert (await http(port, "GET", "/config/editable", {"Host": "localhost:%d" % port}))[0] == 403      # overlay pages' address
        assert (await http(port, "GET", "/config/editable", {"Origin": "http://localhost:%d" % port}))[0] == 403
        change = {"settings": {"twitch": "attacker"}}
        assert (await post(port, "/config", change, {"Origin": "http://evil.example", "Content-Type": "application/json"}))[0] == 403
        assert (await post(port, "/config", change, {"Origin": "http://localhost:%d" % port, "Content-Type": "application/json"}))[0] == 403
        assert (await post(port, "/config", change, same_origin(port, {"Content-Type": "text/plain"})))[0] == 403
        assert (await post(port, "/config", change, same_origin(port, {"Sec-Fetch-Site": "cross-site"})))[0] == 403
    run(serving(local))

    cookie = paired_cookie()

    async def remote(port):
        assert (await http(port, "GET", "/config/editable", cookie))[0] == 403
        assert (await post(port, "/config", {"settings": {"twitch": "attacker"}}, same_origin(port, cookie)))[0] == 403
    run(serving(remote, remote=True))
    assert (folder / "config.json").read_text() == before and hub.CFG["twitch"] == "mine"


def test_saving_writes_config_json_in_one_step_and_keeps_everything_else(home):
    folder = home({"twitch": "old_name", "mystery": {"keep": True}, "logs": {"enabled": True, "keep_days": 90, "extra": "x"}, **SECRETS})
    path = folder / "config.json"
    before = path.read_text()

    async def test(port):
        status, _, body = await post(port, "/config", {"settings": {"twitch": "https://www.twitch.tv/New_Name", "logs.keep_days": 30,
                                                                    "x.title": "  Live:  building  "}})
        assert status == 200
        return json.loads(body)
    answer = run(serving(test))
    assert answer["ok"] is True and answer["restart_needed"] is True and answer["restart"] == ["twitch"]
    assert "Restart OBS to apply: Twitch channel" in answer["why"]
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["twitch"] == "new_name"                          # cleaned the way the hub reads channels
    assert saved["logs"] == {"enabled": True, "keep_days": 30, "extra": "x"}
    assert saved["x"] == {"title": "Live:  building"}             # only what changed is added
    assert saved["mystery"] == {"keep": True} and saved["kick_client_secret"] == SECRETS["kick_client_secret"]
    assert (folder / "config.json.bak").read_text() == before     # the old file, kept once
    assert not os.path.exists(str(path) + ".tmp")
    # applied now where it can be; the channel waits for the restart (the hub keeps reading the old one until then)
    assert hub.LOG.keep_days == 30 and hub.CFG["logs"]["keep_days"] == 30 and hub.TWITCH == "old_name"


def test_every_value_is_checked_and_nothing_is_written_when_one_is_wrong(home):
    folder = home({"twitch": "mine"})
    path = folder / "config.json"
    before = path.read_text()
    wrong = [
        ({"twitch": "not a channel!"}, "isn't a Twitch channel"),
        ({"youtube": "x" * 300}, "too long"),
        ({"facebook": "yes"}, "on or off"),
        ({"logs.keep_days": 0}, "between 1 and 3650"),
        ({"logs.keep_days": 2.5}, "whole number"),
        ({"logs.keep_days": True}, "whole number"),
        ({"close_window_seconds_after_stream": 99999}, "between 0 and 3600"),
        ({"remote.port": 80}, "between 1024 and 65535"),
        ({"x.title": "line one\nline two"}, "one line"),
        ({"x.title_file": "C:\\no\\such\\file.txt"}, "no file"),
        ({"window": "custom"}, "no custom window position"),
        ({"window": "left"}, "right edge"),
        ({"kick_client_secret": "steal"}, "can't be changed here"),
        ({"obs.password": "x"}, "can't be changed here"),
        ({"twitch": "fine", "port": 1}, "can't be changed here"),
    ]

    async def test(port):
        for change, why in wrong:
            status, _, body = await post(port, "/config", {"settings": change})
            answer = json.loads(body)
            assert status == 200 and answer["ok"] is False and why in answer["why"], (change, answer)
        clash = json.loads((await post(port, "/config", {"settings": {"remote.port": port}}))[2])
        assert clash["ok"] is False and "port of its own" in clash["why"]
        assert (await http(port, "POST", "/config", same_origin(port), b"[1, 2]"))[0] == 400
    run(serving(test))
    assert path.read_text() == before and not (folder / "config.json.bak").exists()


def test_a_damaged_config_json_is_never_overwritten(home):
    folder = home({"twitch": "mine"})
    (folder / "config.json").write_text('{"twitch": "mine", oops', encoding="utf-8")
    answer, changes = settings_ui.save(str(folder / "config.json"), {"settings": {"twitch": "other"}}, hub.CFG, hub.channel, hub.PORT)
    assert answer["ok"] is False and "couldn't be read" in answer["why"] and changes == {}
    assert (folder / "config.json").read_text() == '{"twitch": "mine", oops'


def test_saving_with_no_config_json_yet_creates_one(home):
    folder = home()
    answer, changes = settings_ui.save(str(folder / "config.json"), {"twitch": "first_channel"}, hub.CFG, hub.channel, hub.PORT)
    assert answer["ok"] and changes == {"twitch": "first_channel"}
    assert json.loads((folder / "config.json").read_text()) == {"twitch": "first_channel"}
    assert not (folder / "config.json.bak").exists()


def test_unchanged_values_write_nothing(home):
    folder = home({"twitch": "https://twitch.tv/Mine", "logs": {"keep_days": 90}})
    before = (folder / "config.json").read_text()
    answer, changes = settings_ui.save(str(folder / "config.json"), {"settings": {"twitch": "mine", "logs.keep_days": 90}}, hub.CFG,
                                       hub.channel, hub.PORT)
    assert answer == {"ok": True, "why": "", "restart_needed": False, "restart": []} and changes == {}
    assert (folder / "config.json").read_text() == before


def test_live_changes_reach_the_hub_and_only_this_pcs_windows_hear_about_them(home):
    home({"x": {"enabled": True, "title": "Old title"}})
    hub.EMOTES.update({"KEKW": "https://cdn.7tv.app/emote/1/1x.webp"})
    here, away = hub.asyncio.Queue(), hub.asyncio.Queue()
    hub.clients.update({here, away})
    hub.local_clients.add(here)

    async def test(port):
        body = {"settings": {"x.title": "New title", "emotes.bttv": False, "emotes.ffz": False, "emotes.7tv": False,
                             "close_window_seconds_after_stream": 30}}
        return json.loads((await post(port, "/config", body))[2])
    answer = run(serving(test))
    assert answer["ok"] and answer["restart_needed"] is False
    assert hub.x_title() == "New title"                            # X reads its settings live
    assert hub.CFG["close_window_seconds_after_stream"] == 30
    assert hub.EMOTES == {}                                        # every emote service off: the pictures go at once
    events = [here.get_nowait() for _ in range(here.qsize())]
    others = [away.get_nowait() for _ in range(away.qsize())]
    config = [e for e in events if e["type"] == "config"]
    assert config and config[0]["settings"]["x.title"] == "New title"
    assert not [e for e in others if e["type"] == "config"]        # paired devices and overlays never get settings
    assert {"type": "emotes", "emotes": {}} in events
    assert "kick_client_secret" not in json.dumps(events)


def test_the_demo_never_changes_settings(home):
    folder = home({"twitch": "mine"}, "--demo")
    before = (folder / "config.json").read_text()

    async def test(port):
        return json.loads((await post(port, "/config", {"settings": {"twitch": "other"}}))[2])
    answer = run(serving(test))
    assert answer["ok"] is False and "demo" in answer["why"]
    assert (folder / "config.json").read_text() == before


def test_the_window_offers_exactly_the_fields_the_hub_accepts():
    app = open(os.path.join(os.path.dirname(hub.__file__), "web", "app.js"), encoding="utf-8").read()
    block = app.split("const CONFIG_FIELDS = [", 1)[1].split("];", 1)[0]
    assert sorted(re.findall(r"key: '([\w.]+)'", block)) == sorted(settings_ui.FIELDS)
