"""Viewer cards (GET /viewer): one viewer's messages this stream and in earlier streams, checked inputs, capped output,
for this PC's window and paired devices only."""
import json
import os
import time

import pytest

import hub
import viewers
from test_companion import http, run, serving

NAMES = hub.NAMES


def msg(p, name, text, t, **more):
    return {"type": "msg", "id": "%s-%s-%d" % (p, name, t), "t": t, "p": p, "name": name, "text": text, "kind": "chat", **more}


def stream(folder, name, events):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name + ".jsonl"), "w", encoding="utf-8") as f:
        for e in events:
            f.write((e if isinstance(e, str) else json.dumps(e, ensure_ascii=False)) + "\n")


@pytest.fixture
def logs(tmp_path):
    folder = str(tmp_path / "logs")
    stream(folder, "2026-10-01_1900", [msg("twitch", "Ann_B", "hello from october", 1000, uid="42"),
                                        msg("twitch", "someone", "hi ann_b", 1001),
                                        msg("youtube", "Ann_B", "same name, other platform", 1002)])
    stream(folder, "2026-10-08_1900", [msg("twitch", "ann_b", "back again", 2000, uid="42"),
                                        msg("twitch", "Ann_B", "this one gets deleted", 2001, uid="42"),
                                        {"type": "delete", "id": "twitch-Ann_B-2001"},
                                        "{broken line",
                                        msg("twitch", "Ann_B", "gift time", 2002, kind="event", alert="gift", amount="5 subs", uid="42")])
    stream(folder, "2026-10-15_1900", [msg("twitch", "Ann_B", "now with a new name", 3000, uid="42", first="stream"),
                                        msg("twitch", "Ann_B", "and timed out", 3001, uid="42"),
                                        {"type": "purge", "p": "twitch", "name": "ann_b"}])
    return folder


def test_a_card_has_this_stream_and_earlier_streams_newest_first(logs):
    card = viewers.lookup("twitch", "ann_b", "42", "", folder=logs, current="2026-10-15_1900", platforms=NAMES)
    assert card["ok"] and card["name"] == "Ann_B" and card["count"] == 2 and card["first_seen"] == 3000
    assert [m["text"] for m in card["stream"]] == ["and timed out", "now with a new name"]
    assert all(m.get("gone") for m in card["stream"])             # timed out: every line of theirs went
    assert [m["text"] for m in card["past"]] == ["gift time", "this one gets deleted", "back again", "hello from october"]
    assert [m["stream"] for m in card["past"]] == ["2026-10-08_1900"] * 3 + ["2026-10-01_1900"]
    assert card["past"][1]["gone"] is True and "gone" not in card["past"][2]
    assert card["past_streams"] == 2 and card["truncated"] is False and card["history"] is True
    assert all(m["p"] == "twitch" for m in card["stream"] + card["past"])     # not the YouTube viewer of the same name
    assert "type" not in card["past"][0]


def test_a_search_narrows_both_lists(logs):
    card = viewers.lookup("twitch", "Ann_B", "", "AGAIN", folder=logs, current="2026-10-15_1900", platforms=NAMES)
    assert card["stream"] == [] and [m["text"] for m in card["past"]] == ["back again"]
    assert card["count"] == 2                                       # the counts stay the whole stream's


def test_the_platform_id_wins_over_the_name(logs):
    stream(logs, "2026-10-20_1900", [msg("youtube", "Sam", "I am one Sam", 4000, uid="UCaaa"), msg("youtube", "Sam", "I am another", 4001, uid="UCbbb")])
    card = viewers.lookup("youtube", "Sam", "UCbbb", "", folder=logs, current="2026-10-20_1900", platforms=NAMES)
    assert [m["text"] for m in card["stream"]] == ["I am another"]


def test_without_chat_history_this_stream_comes_from_the_hubs_recent_messages():
    recent = [msg("kick", "turbo", "one", 1), msg("system", "", "Stream started.", 2, kind="note"), msg("kick", "TURBO", "two", 3, first="ever")]
    card = viewers.lookup("kick", "turbo", recent=recent, platforms=NAMES)
    assert [m["text"] for m in card["stream"]] == ["two", "one"] and card["first_ever"] is True and card["past"] == []
    assert card["history"] is False


def test_x_viewers_are_found_by_their_handle_too():
    recent = [msg("x", "Dev Daily", "hello", 1, handle="devdaily")]
    assert viewers.lookup("x", "devdaily", recent=recent, platforms=NAMES)["count"] == 1


@pytest.mark.parametrize("platform, name, uid, q", [
    ("myspace", "ann", "", ""), ("", "ann", "", ""), ("twitch", "", "", ""), ("twitch", "   ", "", ""), ("twitch", "a" * 101, "", ""),
    ("twitch", "ann\nbob", "", ""), ("twitch", "ann", "../../etc", ""), ("twitch", "ann", "x" * 200, ""), ("twitch", "ann", "", "q" * 101),
    ("twitch", "ann", "", "tab\there"),
])
def test_bad_requests_are_refused(platform, name, uid, q):
    with pytest.raises(viewers.ViewerError):
        viewers.lookup(platform, name, uid, q, platforms=NAMES)


def test_only_history_file_names_are_read(logs):
    with open(os.path.join(logs, "notes.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps(msg("twitch", "Ann_B", "not a stream file", 9999)) + "\n")
    card = viewers.lookup("twitch", "Ann_B", folder=logs, current="../../secrets", platforms=NAMES)
    assert all(m["text"] != "not a stream file" for m in card["stream"] + card["past"])
    assert card["stream"] == [] and card["count"] == 0


def test_output_and_reading_are_capped(logs, monkeypatch):
    stream(logs, "2026-10-29_1900", [msg("twitch", "Ann_B", "line %d" % i, 10000 + i) for i in range(viewers.STREAM_LIMIT + 50)])
    card = viewers.lookup("twitch", "Ann_B", folder=logs, current="2026-10-29_1900", platforms=NAMES)
    assert len(card["stream"]) == viewers.STREAM_LIMIT and card["stream"][0]["text"] == "line 249" and card["truncated"] is True
    monkeypatch.setattr(viewers, "PAST_FILES", 1)
    card = viewers.lookup("twitch", "Ann_B", folder=logs, current="2026-10-29_1900", platforms=NAMES)
    assert {m["stream"] for m in card["past"]} == {"2026-10-15_1900"} and card["truncated"] is True
    monkeypatch.setattr(viewers, "PAST_FILES", 60)
    monkeypatch.setattr(viewers, "PAST_BYTES", 300)                 # less than one earlier stream's file
    card = viewers.lookup("twitch", "Ann_B", folder=logs, current="2026-10-29_1900", platforms=NAMES)
    assert len(card["past"]) <= 2 and card["truncated"] is True


def test_this_pc_and_paired_devices_can_look_viewers_up(home):
    home()
    hub.seen.clear()
    hub.LOG.start()
    hub.publish("twitch", "Ann_B", "hi from twitch", uid="42", first="ever")
    hub.publish("twitch", "Ann_B", "second line", uid="42")
    hub.publish("twitch", "Bob", "not ann")

    async def local(port):
        status, _, body = await http(port, "GET", "/viewer?p=twitch&name=ann_b&uid=42")
        card = json.loads(body)
        assert status == 200 and card["count"] == 2 and card["first_ever"] is True and card["history"] is True
        assert [m["text"] for m in card["stream"]] == ["second line", "hi from twitch"]
        status, _, body = await http(port, "GET", "/viewer?p=myspace&name=ann_b")
        assert status == 400 and json.loads(body) == {"ok": False, "why": "Unknown platform."}
        evil = {"Origin": "http://evil.example", "Sec-Fetch-Site": "cross-site"}
        assert (await http(port, "GET", "/viewer?p=twitch&name=ann_b", evil))[0] == 403
        assert (await http(port, "GET", "/viewer?p=twitch&name=ann_b", {"Host": "localhost:%d" % port}))[0] == 403    # overlay pages
        assert (await http(port, "GET", "/viewer?p=twitch&name=ann_b", {"Origin": "http://localhost:%d" % port}))[0] == 403
    run(serving(local))

    code, _ = hub.DEV.start_pairing()
    cookie = {"Cookie": "cc_device=" + hub.DEV.pair(code, "Phone")}

    async def remote(port):
        status, _, body = await http(port, "GET", "/viewer?p=twitch&name=ann_b", cookie)
        assert status == 200 and json.loads(body)["count"] == 2
        assert (await http(port, "GET", "/viewer?p=twitch&name=ann_b"))[0] == 401           # not paired
    run(serving(remote, remote=True))
    hub.LOG.stop()


def test_the_demo_never_shows_real_chat_history(home):
    folder = home({}, "--demo")
    stream(str(folder / "logs"), "2026-10-01_1900", [msg("twitch", "Ann_B", "a real past line", int(time.time() * 1000))])

    async def test(port):
        return json.loads((await http(port, "GET", "/viewer?p=twitch&name=Ann_B"))[2])
    card = run(serving(test))
    assert card["ok"] and card["past"] == [] and card["history"] is False
