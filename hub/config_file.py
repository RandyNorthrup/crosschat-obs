"""Switches the CrossChat window flips in config.json itself (the update notice, Tailscale for the companion), so the
file stays the one place settings live."""
import json
import os


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
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(path + ".tmp", path)
