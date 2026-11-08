"""What the hub, its web pages and the extension must agree on, read from the source files.

The hub is the authority. The copies in JavaScript have drifted apart from it before (a reply's voice name, the default
read-aloud mode), so each copy is compared here. A change to one side fails until the other side is changed too.
"""
import inspect
import json
import os
import re

import emotes
import hub

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def source(*path):
    with open(os.path.join(ROOT, *path), encoding="utf-8") as f:
        return f.read()


APP = source("hub", "web", "app.js")
THEME = source("hub", "web", "theme.js")
WIDGETS = source("hub", "web", "widgets.js")
STUDIO = source("hub", "web", "studio.js")
ICONS = source("hub", "web", "icons.js")
BACKGROUND = source("extension", "background.js")
COMMON = source("extension", "common.js")
HUB = source("hub", "hub.py")
VIEWERS = source("hub", "viewers.py")


def body(text, name):
    """What is inside the brackets of `const name = {...}` or `[...]`."""
    rest = text.split("const %s = " % name, 1)[1]
    return rest[1:rest.index({"{": "}", "[": "]"}[rest[0]])]


def number(text, name):
    """The number in `name = 123` (a const or one of several on a line)."""
    return int(re.search(r"\b%s = (\d+)" % name, text).group(1))


def words(text, name):
    return re.findall(r"'(\w+)'", body(text, name))


def limits(text):
    return {k: int(v) for k, v in re.findall(r"(\w+): (\d+)", body(text, "LIMIT"))}


def test_the_reply_limits_are_the_hubs():
    assert limits(APP) == hub.LIMIT
    extension = limits(BACKGROUND)
    assert extension == {p: hub.LIMIT[p] for p in extension}
    assert set(extension) == set(hub.LIMIT) - {"twitch", "kick"}  # those two the hub does itself, through their APIs


def test_every_list_of_platforms_is_the_hubs():
    names = dict(re.findall(r"(\w+): \['([^']+)'", body(APP, "NAMES")))
    assert names == hub.NAMES
    assert dict(re.findall(r"(\w+): '([^']+)'", body(STUDIO, "PLATFORM_NAMES"))) == hub.NAMES
    assert dict(re.findall(r"(\w+): '([^']+)'", body(ICONS, "NAMES"))) == hub.NAMES
    extension = dict(re.findall(r"(\w+): '([^']+)'", body(BACKGROUND, "NAME")))
    assert extension == {p: hub.NAMES[p] for p in extension} and set(extension) == set(limits(BACKGROUND))
    told = re.search(r"THROUGH_EXTENSION = '([^']+)'", APP).group(1)   # what the notice in the chat window names
    assert set(re.split(r", | and ", told)) == {hub.NAMES[p] for p in extension}
    assert set(re.findall(r"(\w+): '", body(WIDGETS, "SHORT"))) == set(hub.NAMES)
    assert set(re.findall(r"(\w+): '#", body(STUDIO, "BRAND"))) == set(hub.NAMES)
    assert set(words(THEME, "PLATFORMS")) == set(hub.NAMES)
    assert set(words(APP, "TTS_PLATFORMS")) == set(hub.NAMES)
    assert set(re.findall(r"^\s+(\w+): '#", THEME.split("colors: {", 1)[1].split("}", 1)[0], re.M)) >= set(hub.NAMES)


def test_the_short_platform_tags_are_one_list():
    short = dict(re.findall(r"(\w+): \['[^']+', '([^']+)'\]", body(APP, "NAMES")))
    assert short == dict(re.findall(r"(\w+): '([^']+)'", body(WIDGETS, "SHORT")))


def test_reading_aloud_is_the_hubs():
    modes = re.search(r'body\.get\("read"\) in \(([^)]*)\)', HUB).group(1)
    assert set(re.findall(r'"(\w+)"', modes)) == set(words(APP, "TTS_READ"))
    default = re.search(r"\bTTS_READ_DEFAULT = '(\w+)'", APP).group(1)
    assert default == hub.TTS_DEFAULTS["read"] == hub.clean_tts({"read": "nonsense"})["read"]
    assert len(hub.clean_tts({"voice": "v" * 999})["voice"]) == number(APP, "TTS_VOICE_MOST")
    assert len(hub.clean_tts({"command": "!" * 999})["command"]) == number(APP, "TTS_COMMAND_MOST")
    fallback, lowest, highest, unset = map(int, re.search(r"max_chars: Math\.round\(num\(s\.max_chars \|\| (\d+), (\d+), (\d+), (\d+)\)\)", APP).groups())
    assert fallback == unset == hub.TTS_DEFAULTS["max_chars"] == hub.clean_tts({})["max_chars"]
    assert hub.clean_tts({"max_chars": 1})["max_chars"] == lowest
    assert hub.clean_tts({"max_chars": 99999})["max_chars"] == highest
    slowest, fastest = map(float, re.search(r"rate: Math\.round\(num\(s\.rate \|\| 1, ([\d.]+), ([\d.]+), 1\)", APP).groups())
    assert hub.clean_tts({"rate": 0.01})["rate"] == slowest
    assert hub.clean_tts({"rate": 99})["rate"] == fastest


def test_quick_replies_and_filters_are_the_hubs(tmp_path, monkeypatch):
    quick = tmp_path / "quick.json"
    quick.write_text(json.dumps(["q" * 500] * 500), encoding="utf-8")
    monkeypatch.setattr(hub, "quick_path", lambda: str(quick))
    assert len(hub.quick_replies()) == number(APP, "QUICK_MAX")
    assert len(hub.quick_replies()[0]) == number(APP, "QUICK_LENGTH")

    most, longest = number(APP, "LIST_MAX"), number(APP, "LIST_LENGTH")
    hub.clean_filters({"words": ["w" * longest] * most, "users": []})   # as many and as long as the page lets through
    for too_much in (["w"] * (most + 1), ["w" * (longest + 1)]):
        try:
            hub.clean_filters({"words": too_much, "users": []})
        except ValueError:
            continue
        raise AssertionError("the hub takes more than the page lets through")


def test_a_viewer_name_and_search_are_as_long_as_the_hub_takes():
    longest = number(APP, "VIEWER_LENGTH")
    assert int(re.search(r"len\(name\) <= (\d+)", VIEWERS).group(1)) == longest
    assert int(re.search(r"len\(q\) > (\d+)", VIEWERS).group(1)) == longest


def test_the_chat_window_waits_as_long_as_the_hub():
    assert number(APP, "YOUTUBE_MOD_MS") == hub.YT_MOD_SECONDS * 1000
    assert number(APP, "JOB_MS") == inspect.signature(hub.by_executor).parameters["seconds"].default * 1000


def test_the_widgets_are_the_hubs():
    assert re.search(r"\\/overlay\\/\(([\w|]+)\)", WIDGETS).group(1).split("|") == list(hub.WIDGETS)
    drawn = re.search(r"const cls = \{([^}]*)\}", WIDGETS).group(1)
    assert set(re.findall(r"(\w+):", drawn)) == set(hub.WIDGETS)
    assert set(re.findall(r"^    (\w+): \{ label:", STUDIO, re.M)) == set(hub.WIDGETS)


def test_the_overlay_may_load_every_emote_picture_it_can_be_given():
    allowed = re.search(r"img-src ([^;]*);", hub.OVERLAY_CSP).group(1).split()
    hosts = re.findall(r"https://([\w.-]+)/emoticons", WIDGETS + APP)
    hosts += [host.replace("\\.", ".") for host in re.match(r"https://\(([^)]*)\)", emotes.PICTURE.pattern).group(1).split("|")]
    assert hosts and all("https://" + host in allowed for host in hosts)


def test_a_feed_request_holds_no_more_lines_than_the_hub_reads():
    reads = re.findall(r"for line in lines\[:(\d+)\]", HUB)
    assert len(reads) == 3 and {int(n) for n in reads} == {number(COMMON, "BATCH_MOST")}   # TikTok, Facebook, Instagram


def test_every_part_carries_the_same_version():
    manifest = json.loads(source("extension", "manifest.json"))["version"]
    script = re.search(r'local VERSION = "([\d.]+)"', source("obs", "crosschat.lua")).group(1)
    project = re.search(r'^version = "([\d.]+)"', source("pyproject.toml"), re.M).group(1)
    assert hub.VERSION == manifest == script == project


def test_the_widgets_may_read_settings_at_either_address():
    for address in ("127.0.0.1:%d" % hub.PORT, "localhost:%d" % hub.PORT):
        assert hub.refused("GET", {"host": address, "sec-fetch-site": "same-origin"}, "/settings") == ""
    assert "connect-src 'self'" in hub.OVERLAY_CSP
