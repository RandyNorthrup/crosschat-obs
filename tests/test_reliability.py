"""Staying up: a message CrossChat can't read is skipped, a job that fails on something unexpected starts again, and
what goes wrong is told instead of passing in silence."""
import asyncio
import errno
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time

import chatlog
import config_file
import devices
import discord_relay
import hub
import kick_api
import pytest
import requests
import rumble_api
import settings_ui
import setup_config
import twitch_api
import vault
from test_companion import http, post, run, serving


class FakeReader:
    def __init__(self, lines):
        self.lines = [line.encode() + b"\r\n" for line in lines]

    async def readline(self):
        if self.lines:
            return self.lines.pop(0)
        await asyncio.sleep(3600)                  # then quiet, like a chat with nobody talking


class FakeWriter:
    def write(self, data):
        pass

    async def drain(self):
        pass

    def close(self):
        pass


def test_one_unreadable_twitch_line_is_skipped(home, monkeypatch):
    home()
    lines = [":tmi.twitch.tv 366 justinfan1 #chan :End of /NAMES list",
             "@badges=;display-name=Bad;id=b1 :bad!bad@bad.tmi.twitch.tv PRIVMSG #chan :this one breaks",
             "@badges=;display-name=Good;id=g1 :good!good@good.tmi.twitch.tv PRIVMSG #chan :still here"]

    async def connection(*args, **kwargs):
        return FakeReader(lines), FakeWriter()

    real_tags = hub.irc_tags

    def tags(raw):
        if "Bad" in raw:
            raise ValueError("a format CrossChat has never seen")
        return real_tags(raw)

    monkeypatch.setattr(hub.asyncio, "open_connection", connection)
    monkeypatch.setattr(hub, "irc_tags", tags)
    hub.skipped.seen.clear()

    async def run():
        task = asyncio.create_task(hub.twitch("chan"))
        await asyncio.sleep(0.2)
        task.cancel()
    asyncio.run(run())
    said = [m["text"] for m in hub.messages if m["p"] == "twitch"]
    assert said == ["still here"] and hub.status["twitch"] == "on"          # same connection, nothing dropped
    assert hub.health["twitch"]["reconnects"] == 0


def test_a_job_that_fails_starts_again(home, monkeypatch):
    home()
    runs = []

    async def job():
        runs.append(1)
        if len(runs) < 3:
            raise KeyError("platform changed something")
        return "done"

    async def no_wait(seconds):
        pass

    monkeypatch.setattr(hub.asyncio, "sleep", no_wait)
    assert asyncio.run(hub.keep_running("twitch", job)) == "done" and len(runs) == 3
    assert hub.status["twitch"] == "retry"


# ---- helpers for the tests below --------------------------------------------------------------------------------------
QUIET = {"emotes": {"bttv": False, "ffz": False, "7tv": False}, "remote": {"enabled": False}}
real_sleep = asyncio.sleep


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def up_and_down(monkeypatch, during=None):
    """hub.main() on a free port of this PC, with a streaming app that closes at once. What main() returned."""
    async def app():
        if during:
            await during()

    async def no_emotes():
        pass
    monkeypatch.setattr(hub, "follow_app", app)
    monkeypatch.setattr(hub, "emotes_refresh", no_emotes)
    monkeypatch.setattr(hub, "PORT", free_port())
    monkeypatch.setattr(hub, "streaming", asyncio.Event())             # (a hub's event belongs to its own event loop)
    monkeypatch.setattr(hub, "ready", None)
    return asyncio.run(hub.main())


def notes():
    return [m["text"] for m in hub.messages if m["kind"] == "note"]


@pytest.fixture
def log_file(tmp_path):
    """Where start_log writes; the handlers it adds to the root logger come off again after the test."""
    root = logging.getLogger()
    before, level = list(root.handlers), hub.log.level
    yield tmp_path / "hub.log"
    for handler in [h for h in root.handlers if h not in before]:
        root.removeHandler(handler)
        handler.close()
    hub.log.setLevel(level)


# ---- what's wrong with config.json is told ------------------------------------------------------------------------------
def test_a_broken_config_reaches_the_log_and_then_the_person_at_the_pc(home, monkeypatch, log_file):
    home("{ not json", "--log", str(log_file))
    assert hub.PORT == 4466 and hub.TWITCH == ""                       # the defaults, as before
    hub.start_log()
    assert "could not be read" in log_file.read_text(encoding="utf-8")  # there even if the hub gets no further
    up_and_down(monkeypatch)
    assert sum("could not be read" in text for text in notes()) == 1
    assert log_file.read_text(encoding="utf-8").count("could not be read") == 1


def test_a_channel_that_cannot_be_used_is_told(home, monkeypatch, log_file):
    home({"twitch": "not a channel!", **QUIET}, "--log", str(log_file))
    hub.start_log()
    assert "'not a channel!' is not a twitch channel" in log_file.read_text(encoding="utf-8")
    up_and_down(monkeypatch)
    assert any("not a twitch channel" in text for text in notes())


@pytest.mark.parametrize("config, used", [({"port": "abc"}, 4466), ({"port": 70000}, 4466), ({"port": None}, 4466)])
def test_a_port_that_is_no_port_does_not_stop_the_hub(home, config, used):
    home(config)
    assert hub.PORT == used and any("port" in text for text in hub.problems)


def test_a_setting_of_the_wrong_kind_does_not_stop_the_hub(home):
    home({"x": 5, "logs": True, "obs": "local", "kick_chatroom": "abc", "remote": {"port": "abc"}, "twitch": "fine"})
    assert hub.X == {} and hub.KICK_ROOM == 0 and hub.remote_port() == 4467 and hub.TWITCH == "fine"
    assert len(hub.problems) == 5


@pytest.mark.parametrize("section", ["emotes", "x", "logs", "remote", "obs", "updates", "overlay"])
def test_a_section_set_to_false_still_just_means_off(home, section):
    """"emotes": false has always switched the emotes off."""
    home({section: False})
    assert hub.problems == []
    assert hub.X == {} and (section != "emotes" or hub.CFG["emotes"] == {})


# ---- when the hub's port is taken ----------------------------------------------------------------------------------------
def test_another_crosschat_hub_on_the_port_ends_quietly_with_code_3(home, monkeypatch):
    home(QUIET)
    told = []
    monkeypatch.setattr(hub, "warn", lambda text, logged=False: told.append(text))

    async def test():
        other = await asyncio.start_server(hub.serve, "127.0.0.1", 0)  # another hub: it really answers
        monkeypatch.setattr(hub, "PORT", other.sockets[0].getsockname()[1])
        try:
            return await hub.main()
        finally:
            other.close()
    assert asyncio.run(test()) == 3 and told == []


async def something_else_on_a_port(reply):
    async def answer(reader, writer):
        await reader.readline()
        writer.write(reply)
        await writer.drain()
        writer.close()
    return await asyncio.start_server(answer, "127.0.0.1", 0)


@pytest.mark.parametrize("reply", [b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nConnection: close\r\n\r\nhello",
                                   b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}', b"", b"not http at all\r\n\r\n"])
def test_anything_else_on_the_port_is_reported_and_ends_with_code_1(home, monkeypatch, reply):
    home(QUIET)
    told = []
    monkeypatch.setattr(hub, "warn", lambda text, logged=False: told.append(text))

    async def test():
        other = await something_else_on_a_port(reply)
        monkeypatch.setattr(hub, "PORT", other.sockets[0].getsockname()[1])
        try:
            return await hub.main()
        finally:
            other.close()
    assert asyncio.run(test()) == hub.PORT_TAKEN
    assert len(told) == 1 and "port" in told[0] and "another CrossChat" not in told[0]


def test_the_message_box_stays_up_until_it_is_answered(home, monkeypatch):
    """A message box is a thread of this program: leaving would take it away before anyone could read it."""
    home(QUIET)
    answered = []

    def fake_box():
        time.sleep(0.2)
        answered.append(1)

    def warn(text, logged=False):
        box = threading.Thread(target=fake_box, daemon=True)
        box.start()
        return box
    monkeypatch.setattr(hub, "warn", warn)

    async def test():
        other = await something_else_on_a_port(b"")
        monkeypatch.setattr(hub, "PORT", other.sockets[0].getsockname()[1])
        try:
            return await hub.main()
        finally:
            other.close()
    assert asyncio.run(test()) == hub.PORT_TAKEN and answered == [1]


def holder(reply):
    """Something holding a port of this PC, answering every connection with `reply`. (port, stop)"""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()

    def serve_them():
        while True:
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            connection.recv(4096)
            connection.sendall(reply)
            connection.close()
    threading.Thread(target=serve_them, daemon=True).start()
    return listener.getsockname()[1], listener.close


@pytest.mark.parametrize("body, code", [(b'{"version": "1.8.0"}', 3), (b"<html>someone else</html>", 4)])
def test_the_exit_code_is_what_the_obs_script_reads(tmp_path, body, code):
    """The real thing, as a process of its own: the OBS script's watchdog goes by this code."""
    port, stop = holder(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s" % (len(body), body))
    try:
        done = subprocess.run([sys.executable, os.path.join(hub.HERE, "hub.py"), "--config", str(tmp_path / "config.json"), "--port", str(port),
                               "--quiet", "--log", str(tmp_path / "hub.log")], timeout=60, capture_output=True, cwd=tmp_path)
    finally:
        stop()
    assert done.returncode == code, done.stderr.decode(errors="replace")


# ---- chat history must never get in the way of chat ------------------------------------------------------------------
class FullDisk:
    def write(self, text):
        raise OSError(errno.ENOSPC, "No space left on device")

    def flush(self):
        raise OSError(errno.ENOSPC, "No space left on device")

    def close(self):
        raise OSError(errno.ENOSPC, "No space left on device")


def test_a_full_disk_costs_the_history_not_the_chat(home):
    home({})
    window = asyncio.Queue()
    hub.clients.add(window)
    hub.LOG.file, hub.LOG.name = FullDisk(), "2026-01-01_1200"
    hub.publish("twitch", "ann", "still shown", mid="tw-1")
    hub.send({"type": "delete", "id": "tw-1"})
    hub.publish("twitch", "ann", "and this", mid="tw-2")
    seen = [window.get_nowait() for _ in range(window.qsize())]
    assert [e["text"] for e in seen if e.get("p") == "twitch"] == ["still shown", "and this"] and {"type": "delete", "id": "tw-1"} in seen
    assert hub.LOG.file is None
    assert sum("chat history" in text for text in notes()) == 1        # told once


def test_a_history_folder_that_cannot_be_made_does_not_stop_the_stream(home, monkeypatch):
    folder = home({})
    (folder / "logs").write_text("a file where the folder should be", encoding="utf-8")
    monkeypatch.setattr(hub, "streaming", asyncio.Event())
    asyncio.run(hub.stream_started(local=True))
    assert hub.streaming.is_set() and any("chat history" in text for text in notes())


def test_a_line_cut_off_by_a_full_disk_does_not_break_chat_history(tmp_path):
    log = chatlog.ChatLog(str(tmp_path))
    good = json.dumps({"type": "msg", "id": "a", "t": 1000, "p": "twitch", "name": "ann", "text": "hi", "kind": "chat"}).encode()
    (tmp_path / "2026-01-01_1200.jsonl").write_bytes(good + b"\n" + '{"type": "msg", "text": "€'.encode("utf-8")[:-1])     # half a character
    assert log.listing()[0]["messages"] == 1
    assert [m["text"] for m in log.messages("2026-01-01_1200")] == ["hi"]


def test_a_chat_line_python_cannot_encode_does_not_break_the_history(tmp_path):
    log = chatlog.ChatLog(str(tmp_path))
    name = log.start()
    log.write({"type": "msg", "text": "half an emoji \ud83d"})
    log.stop()
    assert log.messages(name)[0]["text"].startswith("half an emoji")


def test_opening_chat_history_does_not_stop_the_event_loop(home, monkeypatch):
    home({})
    where = {}
    for name, answer in (("listing", []), ("messages", []), ("csv", b"x"), ("html", b"x")):
        monkeypatch.setattr(hub.LOG, name, lambda *a, name=name, answer=answer: where.update({name: threading.current_thread().name}) or answer)

    async def test(port):
        for path in ("/logs", "/logs/2026-01-01_1200.json", "/logs/2026-01-01_1200.csv", "/logs/2026-01-01_1200.html"):
            assert (await http(port, "GET", path))[0] == 200, path
    run(serving(test))
    assert set(where) == {"listing", "messages", "csv", "html"} and all(n.startswith("viewer") for n in where.values())


def test_the_html_export_colours_every_platform(home):
    folder = home({})
    (folder / "logs").mkdir()
    rows = [{"type": "msg", "id": p, "t": 1000, "p": p, "name": "n", "text": "t", "kind": "chat"} for p in hub.NAMES]
    (folder / "logs" / "2026-01-01_1200.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    page = hub.LOG.html("2026-01-01_1200").decode()
    assert page.count('style="color:') == len(hub.NAMES) and 'style="color:#888"' not in page


# ---- unexpected errors reach the log ----------------------------------------------------------------------------------
def test_other_libraries_errors_reach_crosschat_log(home, log_file):
    home({}, "--log", str(log_file))
    hub.start_log()
    logging.getLogger("asyncio").error("the event loop says something went wrong")
    assert "the event loop says" in log_file.read_text(encoding="utf-8")


def test_what_the_event_loop_cannot_hand_back_reaches_the_log(home, monkeypatch, log_file):
    home(QUIET, "--log", str(log_file))
    hub.start_log()

    async def during():
        asyncio.get_running_loop().call_exception_handler({"message": "nobody was waiting for this", "exception": KeyError("the details")})
    up_and_down(monkeypatch, during)
    written = log_file.read_text(encoding="utf-8")
    assert "unexpected: nobody was waiting for this" in written and "the details" in written


def test_a_job_nobody_waits_for_is_kept_and_its_failure_logged(home, monkeypatch, caplog):
    home({})

    async def broken(job):
        raise ValueError("went wrong in the background")
    monkeypatch.setattr(hub, "run_send", broken)

    async def test():
        assert hub.new_send({"text": "hi", "to": ["twitch"]})["ok"] is True
        assert len(hub.background) == 1                                # kept: the loop only holds a weak reference
        await real_sleep(0.01)
        assert not hub.background
    asyncio.run(test())
    failed = [r for r in caplog.records if r.name == "crosschat" and r.exc_info]
    assert len(failed) == 1 and "went wrong in the background" in str(failed[0].exc_info[1])


# ---- sign-ins that can't be read say so ---------------------------------------------------------------------------------
SAVED = [("Twitch", lambda path: twitch_api.Twitch("client", path)),
         ("Kick", lambda path: kick_api.Kick("client", "secret", path, "http://localhost:4466/kick/callback")),
         ("Rumble", rumble_api.Rumble),
         ("Discord", lambda path: discord_relay.Discord(path, hub.NAMES))]


@pytest.mark.parametrize("name, make", SAVED)
def test_nothing_saved_is_simply_not_connected(tmp_path, name, make):
    saved = make(str(tmp_path / "saved.bin"))
    assert saved.why == "" and saved.state()["state"] == "off"


@pytest.mark.parametrize("name, make", SAVED)
def test_a_sign_in_that_cannot_be_read_says_so(tmp_path, name, make):
    path = tmp_path / "saved.bin"
    path.write_bytes(b"not something CrossChat sealed")
    saved = make(str(path))
    assert name in saved.why and saved.state()["state"] == "error"


@pytest.mark.parametrize("name, make, module", [(*SAVED[0], twitch_api), (*SAVED[1], kick_api), (*SAVED[2], rumble_api), (*SAVED[3], discord_relay)])
def test_a_sign_in_of_the_wrong_shape_says_so_too(tmp_path, monkeypatch, name, make, module):
    path = tmp_path / "saved.bin"
    path.write_bytes(b"sealed")
    monkeypatch.setattr(module, "unprotect", lambda data: b"[1, 2, 3]")
    saved = make(str(path))
    assert name in saved.why and saved.state()["state"] == "error"


def test_a_keyring_that_does_not_answer_is_named():
    assert "keyring" in vault.unreadable(vault.Unavailable("no keyring"), "Twitch sign-in")


# ---- reading the sign-ins doesn't hold up the hub ------------------------------------------------------------------------
def test_the_hub_answers_while_a_keyring_is_being_unlocked(home, monkeypatch):
    home(QUIET)
    real_setup, seen = hub.companion_setup, {}

    def slow_setup():                                                   # here the keyring waits for someone to unlock it
        address = "http://127.0.0.1:%d" % hub.PORT
        seen["version"] = requests.get(address + "/version", timeout=2).json()
        with pytest.raises(requests.ReadTimeout):                       # everything else needs the sign-ins: it waits for them
            requests.get(address + "/whoami", timeout=0.3)
        real_setup()
    monkeypatch.setattr(hub, "companion_setup", slow_setup)
    up_and_down(monkeypatch)
    assert seen["version"] == {"version": hub.VERSION}


# ---- chat source failures reach the log, once per kind ---------------------------------------------------------------
def failing(*a, **k):
    raise requests.ConnectionError("the platform did not answer")


async def a_few_rounds(job):
    """Run a job that never ends for a moment, with its waits cut short."""
    task = asyncio.create_task(job)
    for _ in range(40):
        await real_sleep(0.005)
    task.cancel()


@pytest.fixture
def quick_waits(monkeypatch):
    async def sleep(seconds):
        await real_sleep(0)
    monkeypatch.setattr(hub.asyncio, "sleep", sleep)
    monkeypatch.setattr(hub, "streaming", asyncio.Event())
    hub.skipped.seen.clear()
    hub.streaming.set()


def logged(caplog, words):
    return [r.getMessage() for r in caplog.records if r.name == "crosschat" and words in r.getMessage()]


def test_a_twitch_connection_that_keeps_failing_is_logged_once(home, monkeypatch, quick_waits, caplog):
    home({})

    async def refused(*a, **k):
        raise OSError("connection refused")
    monkeypatch.setattr(hub.asyncio, "open_connection", refused)
    asyncio.run(a_few_rounds(hub.twitch("chan")))
    assert len(logged(caplog, "connection refused")) == 1


@pytest.mark.parametrize("step, words", [("yt_live_video", "couldn't look up the live video"), ("yt_open", "couldn't open the chat"),
                                         ("yt_poll", "couldn't read the chat")])
def test_each_step_of_youtube_failing_is_logged_once(home, monkeypatch, quick_waits, caplog, step, words):
    home({})
    good = {"yt_live_video": lambda target: "video1234567", "yt_open": lambda video: {"key": "k", "version": "v", "token": "t"}, "yt_poll": failing}
    good[step] = failing
    for name, job in good.items():
        monkeypatch.setattr(hub, name, job)
    asyncio.run(a_few_rounds(hub.youtube("@someone")))
    assert len(logged(caplog, words)) == 1 and "did not answer" in logged(caplog, words)[0]


def test_a_youtube_page_without_its_chat_is_logged(home, monkeypatch, quick_waits, caplog):
    home({})
    monkeypatch.setattr(hub, "yt_live_video", lambda target: "video1234567")
    monkeypatch.setattr(hub, "yt_open", lambda video: None)
    asyncio.run(a_few_rounds(hub.youtube("@someone")))
    assert len(logged(caplog, "couldn't open the chat")) == 1


def test_kicks_chat_feed_lookup_failing_is_logged_once(home, monkeypatch, quick_waits, caplog):
    home({})
    monkeypatch.setattr(hub.requests, "post", failing)
    known = hub.kick_feed(42)
    assert hub.kick_feed(42) == known and len(logged(caplog, "chat feed's address")) == 1


def test_kicks_channel_record_failing_is_logged_once(home, monkeypatch, quick_waits, caplog):
    home({})
    monkeypatch.setattr(hub.requests, "get", failing)
    asyncio.run(a_few_rounds(hub.kick("slug", 0)))
    assert len(logged(caplog, "channel's record")) == 1


def test_kick_refusing_the_channel_record_is_logged(home, monkeypatch, quick_waits, caplog):
    home({})
    monkeypatch.setattr(hub.requests, "get", lambda *a, **k: type("Refused", (), {"status_code": 403})())
    asyncio.run(a_few_rounds(hub.kick("slug", 0)))
    assert "HTTP 403" in logged(caplog, "channel's record")[0]


def test_a_viewer_count_that_keeps_failing_is_logged_once(home, monkeypatch, quick_waits, caplog):
    home({"twitch": "someone"})
    monkeypatch.setattr(hub, "twitch_viewers", failing)
    asyncio.run(a_few_rounds(hub.audience()))
    assert len(logged(caplog, "viewer count")) == 1 and hub.viewers["twitch"] is None


# ---- damaged settings files are kept and told ----------------------------------------------------------------------------
@pytest.mark.parametrize("content", ["{ not json", "[1, 2]", '{"words": "not a list"}', '{"words": ["' + "x" * 51 + '"]}'])
def test_damaged_filters_are_kept_and_told(home, monkeypatch, content):
    folder = home({})
    (folder / "filters.json").write_text(content, encoding="utf-8")
    home({})
    assert hub.FILTERS == hub.FILTER_DEFAULTS and not (folder / "filters.json").exists()
    assert (folder / "filters.json.bad").read_text(encoding="utf-8") == content
    assert any("your chat filters" in text and "filters.json.bad" in text for text in hub.problems)


def test_damaged_settings_reach_the_person_at_the_pc_once_the_hub_is_up(home, monkeypatch, log_file):
    folder = home({**QUIET})
    (folder / "filters.json").write_text("{ not json", encoding="utf-8")
    home({**QUIET}, "--log", str(log_file))
    hub.problems.clear()                                                # (what home()'s own companion_setup found)
    hub.start_log()
    (folder / "filters.json").write_text("{ not json", encoding="utf-8")
    up_and_down(monkeypatch)
    assert sum("your chat filters" in text for text in notes()) == 1
    assert log_file.read_text(encoding="utf-8").count("your chat filters") == 1


def test_damaged_text_to_speech_settings_are_kept_and_told(home):
    folder = home({})
    (folder / "tts.json").write_text('{"rate": "fast"}', encoding="utf-8")
    home({})
    assert hub.TTS == hub.TTS_DEFAULTS and (folder / "tts.json.bad").exists()


def test_saved_settings_are_checked_the_way_the_app_checks_them(home):
    folder = home({})
    (folder / "filters.json").write_text(json.dumps({"words": ["  two   words "], "joins": "yes", "unknown": 1}), encoding="utf-8")
    (folder / "tts.json").write_text(json.dumps({"rate": 9, "volume": -1, "read": "everything", "enabled": True}), encoding="utf-8")
    home({})
    assert hub.FILTERS["words"] == ["two words"] and hub.FILTERS["joins"] is False and "unknown" not in hub.FILTERS
    assert hub.TTS["rate"] == 2.0 and hub.TTS["volume"] == 0.0 and hub.TTS["read"] == "questions" and hub.TTS["enabled"] is True
    assert not (folder / "filters.json.bad").exists() and not (folder / "tts.json.bad").exists()


def test_settings_saved_with_a_byte_order_mark_are_not_damaged(home):
    folder = home({})
    (folder / "filters.json").write_text('{"words": ["hello"]}', encoding="utf-8-sig")
    home({})
    assert hub.FILTERS["words"] == ["hello"] and not (folder / "filters.json.bad").exists()


def test_settings_never_saved_are_simply_the_defaults(home):
    home({})
    assert hub.FILTERS == hub.FILTER_DEFAULTS and hub.problems == []


def test_damaged_quick_replies_are_kept_and_told(home):
    folder = home({})
    (folder / "quick.json").write_text('{"not": "a list"}', encoding="utf-8")
    assert hub.quick_replies() == hub.QUICK_DEFAULTS and (folder / "quick.json.bad").exists()
    assert hub.quick_replies() == hub.QUICK_DEFAULTS                   # the file's out of the way: said once
    assert sum("your quick replies" in text for text in notes()) == 1


@pytest.mark.parametrize("content", ["{ not json", "[]", '{"devices": 5}', "{}"])
def test_damaged_devices_are_kept_and_told(tmp_path, content):
    path = tmp_path / "devices.json"
    path.write_text(content, encoding="utf-8")
    told = []
    d = devices.Devices(str(path), told.append)
    assert d.devices == [] and len(told) == 1 and "pairing again" in told[0]
    assert (tmp_path / "devices.json.bad").read_text(encoding="utf-8") == content
    code, _ = d.start_pairing()
    assert d.pair(code, "Phone") and (tmp_path / "devices.json.bad").read_text(encoding="utf-8") == content    # a new list doesn't touch it


def test_devices_with_an_unusable_entry_are_cleaned_not_lost(tmp_path):
    path = tmp_path / "devices.json"
    path.write_text(json.dumps({"devices": [{"id": "a", "hash": "abc"}, {"id": "b", "hash": 5}, "junk"]}), encoding="utf-8")
    told = []
    assert [x["id"] for x in devices.Devices(str(path), told.append).devices] == ["a"] and told == []


# ---- the port setting -----------------------------------------------------------------------------------------------------
def test_a_port_other_than_4466_is_warned_about(home, monkeypatch):
    home(QUIET)
    up_and_down(monkeypatch)
    assert sum("browser extension only talks to 4466" in text for text in notes()) == 1


def test_the_usual_port_says_nothing_about_it(home, monkeypatch):
    home(QUIET)
    port = free_port()
    monkeypatch.setitem(hub.DEFAULTS, "port", port)                     # (the real 4466 may be in use on this PC)
    monkeypatch.setattr(sys.modules[__name__], "free_port", lambda: port)
    up_and_down(monkeypatch)
    assert not any("only talks to" in text for text in notes())


def test_the_demo_says_nothing_about_its_port(home, monkeypatch):
    home(QUIET, "--demo")
    monkeypatch.setattr(hub, "PORT", free_port())
    monkeypatch.setattr(hub, "streaming", asyncio.Event())
    monkeypatch.setattr(hub, "ready", None)
    told = []                                                           # (the demo's stream start clears the chat, notes and all)
    monkeypatch.setattr(hub, "warn", lambda text, logged=False: told.append(text))

    async def test():                                                   # (the demo runs until it is stopped)
        running = asyncio.create_task(hub.main())
        await real_sleep(0.3)
        running.cancel()
    asyncio.run(test())
    assert hub.ready.is_set() and told == []


# ---- YouTube: every message, or say why not ----------------------------------------------------------------------------
def chat_page(menu):
    chat = {"continuations": [{"reloadContinuationData": {"continuation": "TOP"}}]}
    if menu is not None:
        chat["header"] = {"liveChatHeaderRenderer": {"viewSelector": {"sortFilterSubMenuRenderer": {"subMenuItems": menu}}}}
    return '"INNERTUBE_API_KEY":"k","clientVersion":"v" ytInitialData = ' + json.dumps({"contents": {"liveChatRenderer": chat}})


def item(title, token):
    return {"title": title, "continuation": {"reloadContinuationData": {"continuation": token}}}


def opened(monkeypatch, menu):
    monkeypatch.setattr(hub.web, "get", lambda *a, **k: type("Page", (), {"text": chat_page(menu)})())
    return hub.yt_open("video1234567")


def test_live_chat_is_picked_by_its_name_wherever_it_is_in_the_menu(monkeypatch):
    assert opened(monkeypatch, [item("Top chat", "A"), item("Live chat", "B")]) == {"key": "k", "version": "v", "token": "B"}
    assert opened(monkeypatch, [item("Live chat", "B"), item("Top chat", "A")])["token"] == "B"
    assert opened(monkeypatch, [item({"runs": [{"text": "Live chat"}]}, "B")])["token"] == "B"


@pytest.mark.parametrize("menu", [None, [], [item("Top chat", "A")], [item("Top chat", "A"), item("Something new", "C")], [{"title": "Live chat"}], ["junk"]])
def test_without_live_chat_in_the_menu_it_says_top_chat(monkeypatch, menu):
    assert opened(monkeypatch, menu) == {"key": "k", "version": "v", "token": "TOP", "top_only": True}


def test_falling_back_to_top_chat_is_logged_and_noted_once_a_stream(home, monkeypatch, quick_waits, caplog):
    home({})
    monkeypatch.setattr(hub, "yt_live_video", lambda target: "video1234567")
    monkeypatch.setattr(hub, "yt_open", lambda video: {"key": "k", "version": "v", "token": "t", "top_only": True})
    monkeypatch.setattr(hub, "yt_poll", lambda chat: None)
    asyncio.run(a_few_rounds(hub.youtube("@someone")))
    assert len(logged(caplog, "showing Top chat only")) == 1 and sum("Top chat" in text for text in notes()) == 1


# ---- covered pages ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name, config", [("x", {"x": {"enabled": True}}), ("tiktok", {"tiktok": "sunny.daze"}), ("facebook", {"facebook": True}),
                                          ("instagram", {"instagram": True})])
def test_a_covered_page_reporting_once_a_minute_stays_live(home, monkeypatch, quick_waits, name, config):
    """Chrome wakes a page in a covered window about once a minute once it has been hidden for five."""
    home(config)
    hub.status[name], hub.state[name + "_seen"] = "on", time.time() - 61
    asyncio.run(a_few_rounds(hub.x_watch()))
    assert hub.status[name] == "on"


# ---- saving settings ----------------------------------------------------------------------------------------------------
def sealed(monkeypatch, module):
    monkeypatch.setattr(module, "protect", lambda data: b"sealed " + data)


def twitch_save(tmp_path, monkeypatch):
    sealed(monkeypatch, twitch_api)
    twitch_api.Twitch("client", str(tmp_path / "saved")).save()


def kick_save(tmp_path, monkeypatch):
    sealed(monkeypatch, kick_api)
    kick_api.Kick("client", "secret", str(tmp_path / "saved"), "http://localhost:4466/kick/callback").save()


def rumble_save(tmp_path, monkeypatch):
    sealed(monkeypatch, rumble_api)
    rumble_api.Rumble(str(tmp_path / "saved")).set("https://rumble.com/-livestream-api/get-data?key=ABCDEFGH12")


def discord_save(tmp_path, monkeypatch):
    sealed(monkeypatch, discord_relay)
    discord_relay.Discord(str(tmp_path / "saved"), hub.NAMES).save()


@pytest.mark.parametrize("write", [
    lambda folder, patch: config_file.change(str(folder / "saved"), "a.b", 1),
    lambda folder, patch: setup_config.write(str(folder / "saved"), {"a": 1}),
    lambda folder, patch: devices.Devices(str(folder / "saved")).save(),
    lambda folder, patch: settings_ui.save(str(folder / "saved"), {"open_window_on_stream_start": False}, {"open_window_on_stream_start": True}, hub.channel),
    twitch_save, kick_save, rumble_save, discord_save])
def test_every_file_is_replaced_in_one_safe_step(tmp_path, monkeypatch, write):
    """Every writer goes to the disk before the old file is replaced, so a power cut can't leave an empty one."""
    forced = []
    monkeypatch.setattr(config_file.os, "fsync", lambda fd: forced.append(fd))
    write(tmp_path, monkeypatch)
    assert forced and (tmp_path / "saved").exists() and not (tmp_path / "saved.tmp").exists()


def test_the_hubs_own_settings_are_saved_safely_too(home, monkeypatch):
    folder = home({})
    forced = []
    monkeypatch.setattr(config_file.os, "fsync", lambda fd: forced.append(fd))

    async def test(port):
        assert json.loads((await post(port, "/quick", {"replies": ["GG"]}))[2]) == {"ok": True}
        assert json.loads((await post(port, "/filters", {"words": ["x"]}))[2]) == {"ok": True}
        assert json.loads((await post(port, "/tts", {"enabled": False}))[2]) == {"ok": True}
    run(serving(test))
    assert len(forced) == 3 and (folder / "quick.json").exists()


def test_a_single_rumble_gift_reads_like_the_others(home):
    home({})
    hub.state["local"], hub.state["since"] = True, 0.0
    last = {"gifts": 0}
    gift = {"num_gifted_subs": 1, "latest_gifted_sub": {"total_gifts": 1, "purchased_by": "Gifter"}}
    hub.rumble_read({"livestreams": [{"id": "7ho8uk", "is_live": True}], "gifted_subs": gift}, [], last)
    assert hub.messages[-1]["amount"] == "a sub" and hub.messages[-1]["system"] == "Gifter gifted a sub"
