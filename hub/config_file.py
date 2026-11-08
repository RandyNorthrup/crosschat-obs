"""Small jobs several parts of CrossChat share: replacing a file in one step, keeping a damaged one out of the way, the
switches the CrossChat window flips in config.json itself (the update notice, Tailscale for the companion, so the file
stays the one place settings live), and the two things the Mac and Linux helpers do alike."""
import json
import os
import threading


def replace_file(path, data):
    """Replace a file in one step: a crash or a full disk leaves the old one, never half a new one. `data` is bytes, or
    text to keep as UTF-8."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path + ".tmp", "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(path + ".tmp", path)


def set_aside(path):
    """Keep a damaged settings file as <path>.bad, for someone to look at and out of the way of the next save. False when
    it couldn't be moved."""
    try:
        os.replace(path, path + ".bad")
        return True
    except OSError:
        return False


def change(path, key, value):
    """Set one setting ("name" or "section.name") in config.json, keeping everything else in it as it was. A missing
    config.json is started; one that can't be read raises ValueError and is left alone."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    except (OSError, UnicodeDecodeError, ValueError):
        raise ValueError("config.json couldn't be read, so CrossChat didn't change it. Fix it (or delete it) first.") from None
    if not isinstance(data, dict):
        raise ValueError("config.json isn't a settings file CrossChat can change.")
    section, _, name = key.partition(".")
    if name:
        if not isinstance(data.get(section), dict):
            data[section] = {}
        data[section][name] = value
    else:
        data[section] = value
    replace_file(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


# ---- macOS and Linux ----------------------------------------------------------------------------------------------
def on_the_side(job, *argv):
    """Moving and closing windows needs no answer: done on the side, so the hub never waits for it."""
    threading.Thread(target=job, args=argv, daemon=True).start()


def process_running(pid):
    """True while process `pid` is there."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:                  # there, but someone else's
        return True
    except OSError:
        return False
    return True
