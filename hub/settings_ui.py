"""Settings → Channels & options in the CrossChat window: the parts of config.json people change, so nobody has to edit
the file by hand.

editable() is what the window shows; save() checks every field, writes config.json in one step (keeping a copy of the
old one as config.json.bak and every key it doesn't know about), and says which changes need OBS restarted;
apply_live() puts the rest to work at once. Tokens, secrets, passwords and paths to other programs are never part of it.
"""
import asyncio
import json
import os
import re

# key -> (kind, detail, needs a restart). Dotted keys are one section deep, like config.json itself.
FIELDS = {
    "twitch": ("channel", "twitch", True),
    "youtube": ("channel", "youtube", True),
    "kick": ("channel", "kick", True),
    "tiktok": ("channel", "tiktok", True),
    "facebook": ("bool", None, True),
    "instagram": ("bool", None, True),
    "broadcaster": ("choice", ("auto", "obs", "streamlabs", "manual"), True),
    "x.enabled": ("bool", None, True),
    "x.auto_go_live": ("bool", None, False),
    "x.title": ("text", 120, False),
    "x.title_file": ("file", 260, False),
    "x.source": ("text", 40, False),
    "window": ("window", None, False),
    "open_window_on_stream_start": ("bool", None, False),
    "close_window_seconds_after_stream": ("int", (0, 3600), False),
    "emotes.bttv": ("bool", None, False),
    "emotes.ffz": ("bool", None, False),
    "emotes.7tv": ("bool", None, False),
    "logs.enabled": ("bool", None, False),
    "logs.keep_days": ("int", (1, 3650), False),
    "remote.enabled": ("bool", None, False),
    "remote.port": ("int", (1024, 65535), False),
}
LABELS = {"twitch": "Twitch channel", "youtube": "YouTube channel", "kick": "Kick channel", "tiktok": "TikTok @name",
          "facebook": "Facebook Live", "instagram": "Instagram Live", "broadcaster": "Streaming app", "x.enabled": "X",
          "x.auto_go_live": "Go live on X by itself", "x.title": "X title",
          "x.title_file": "X title file", "x.source": "X source name", "window": "Window position",
          "open_window_on_stream_start": "Open the window when the stream starts",
          "close_window_seconds_after_stream": "Close the windows after the stream", "emotes.bttv": "BetterTTV emotes",
          "emotes.ffz": "FrankerFaceZ emotes", "emotes.7tv": "7TV emotes", "logs.enabled": "Chat history",
          "logs.keep_days": "Days of chat history kept", "remote.enabled": "Companion", "remote.port": "Companion port"}
CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class SettingsError(ValueError):
    pass


def get(cfg, key):
    section, _, name = key.partition(".")
    if not name:
        return cfg.get(section)
    return (cfg.get(section) or {}).get(name)


def put(cfg, key, value):
    section, _, name = key.partition(".")
    if not name:
        cfg[section] = value
    else:
        if not isinstance(cfg.get(section), dict):
            cfg[section] = {}
        cfg[section][name] = value                 # in place: the hub keeps references to these sections (X, say)


def shown(cfg, key):
    """A field's value as the window shows it."""
    value = get(cfg, key)
    if key == "window":
        return "custom" if isinstance(value, dict) else "auto"
    kind = FIELDS[key][0]
    if kind == "bool":
        return value is True or str(value).lower() in ("on", "yes", "1", "true")
    if kind == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return FIELDS[key][1][0]
    return "" if value is None else str(value)


def editable(cfg):
    """What Settings → Channels & options shows: the editable values, which need a restart, and whether this looks like
    a first run (no channel set up at all)."""
    values = {key: shown(cfg, key) for key in FIELDS}
    first_run = not any(values[k] for k in ("twitch", "youtube", "kick", "tiktok", "facebook", "instagram", "x.enabled"))
    return {"settings": values, "restart": [k for k, f in FIELDS.items() if f[2]],
            "custom_window": isinstance(cfg.get("window"), dict), "first_run": first_run}


def check(key, value, cfg, channel):
    """The value to save for one field, or SettingsError saying what is wrong, in plain words."""
    kind, detail = FIELDS[key][:2]
    label = LABELS[key]
    if kind == "bool":
        if not isinstance(value, bool):
            raise SettingsError("%s must be on or off." % label)
        return value
    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise SettingsError("%s must be a whole number." % label)
        low, high = detail
        if not low <= value <= high:
            raise SettingsError("%s must be between %d and %d." % (label, low, high))
        return value
    if not isinstance(value, str):
        raise SettingsError("%s must be text." % label)
    value = value.strip()
    if kind == "choice":
        if value not in detail:
            raise SettingsError("%s must be one of: %s." % (label, ", ".join(detail)))
        return value
    if kind == "channel":
        if len(value) > 200 or CONTROL.search(value):
            raise SettingsError("That %s is too long." % label)
        cleaned = channel(value, detail)
        if value and not cleaned:
            raise SettingsError("That isn't a %s CrossChat can use. Paste the name or a link to the channel." % label)
        return cleaned
    if kind in ("text", "file"):
        if len(value) > detail or CONTROL.search(value):
            raise SettingsError("%s can be at most %d characters on one line." % (label, detail))
        if kind == "file" and value and not os.path.isfile(os.path.expandvars(value)):
            raise SettingsError("There is no file at %s." % value)
        return value
    if kind == "window":
        if value not in ("auto", "custom"):
            raise SettingsError("The window goes at the right edge (auto) or where config.json says (custom).")
        if value == "custom" and not isinstance(cfg.get("window"), dict):
            raise SettingsError("There is no custom window position in config.json yet; it stays at the right edge.")
        return value
    raise SettingsError("%s can't be changed here." % label)


def before(cfg, key, channel):
    """A field's value now, the way check() would write it (so "twitch.tv/Name" in config.json and "name" agree)."""
    value = shown(cfg, key)
    return channel(value, FIELDS[key][1]) if FIELDS[key][0] == "channel" else value


def save(path, body, cfg, channel, port=None):
    """Check and save the fields in `body` ({"settings": {...}} or the fields themselves). Returns (answer, changes):
    answer is what the window gets ({ok, why, restart_needed, restart}); changes maps each changed field to its new
    value, for apply_live(). port: the one CrossChat itself listens on."""
    fields = body.get("settings") if isinstance(body.get("settings"), dict) else body
    unknown = sorted(str(k)[:40] for k in fields if k not in FIELDS)
    if unknown:
        return {"ok": False, "why": "These can't be changed here: %s." % ", ".join(unknown[:5])}, {}
    try:
        wanted = {key: check(key, value, cfg, channel) for key, value in fields.items()}
    except SettingsError as error:
        return {"ok": False, "why": str(error)}, {}
    main_port = int(port or cfg.get("port") or 4466)
    if wanted.get("remote.port", shown(cfg, "remote.port")) == main_port:
        return {"ok": False, "why": "The companion needs a port of its own (CrossChat itself uses %d)." % main_port}, {}
    changes = {k: v for k, v in wanted.items() if v != before(cfg, k, channel)}
    if not changes:
        return {"ok": True, "why": "", "restart_needed": False, "restart": []}, {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            raw = json.load(f)
        old_text = None
    except FileNotFoundError:
        raw, old_text = {}, ""
    except (OSError, ValueError) as error:
        return {"ok": False, "why": "config.json couldn't be read, so nothing was changed (%s). Fix or delete it, then try again." % error}, {}
    if not isinstance(raw, dict):
        return {"ok": False, "why": "config.json isn't a settings file, so nothing was changed."}, {}
    for key, value in changes.items():
        if key == "window" and value == "custom":
            continue                              # the position already in config.json stays as it is
        put(raw, key, value)
    try:
        if old_text is None:
            with open(path, "rb") as f:
                old = f.read()
            write(path + ".bak", old)
        write(path, (json.dumps(raw, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    except OSError as error:
        return {"ok": False, "why": "Could not save config.json (%s)." % (error.strerror or error)}, {}
    restart = [k for k in changes if FIELDS[k][2]]
    with_obs = wanted.get("broadcaster", shown(cfg, "broadcaster")) in ("auto", "obs", "")
    how = "Restart OBS" if with_obs else "Close CrossChat and open it again"
    why = "Saved. %s to apply: %s." % (how, ", ".join(LABELS[k] for k in restart)) if restart else "Saved."
    return {"ok": True, "why": why, "restart_needed": bool(restart), "restart": restart}, changes


def write(path, data):
    """Replace a file in one step (a crash or a full disk can't leave half a config.json)."""
    with open(path + ".tmp", "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(path + ".tmp", path)


def apply_live(hub, changes):
    """Put saved changes to work now where that is safe; the ones that need a restart only go into the settings the
    window shows."""
    for key, value in changes.items():
        if key == "window":
            if value == "auto":
                hub.CFG["window"] = "auto"
            continue
        put(hub.CFG, key, value)
    if any(k.startswith("emotes.") for k in changes):
        if not any((hub.CFG.get("emotes") or {}).values()):
            hub.EMOTES.clear()
            hub.send({"type": "emotes", "emotes": {}})
        else:
            spawn(hub.load_emotes(hub.state.get("twitch_room", "")))
    if "logs.keep_days" in changes and hub.LOG:
        hub.LOG.keep_days = changes["logs.keep_days"]
    if "remote.enabled" in changes or "remote.port" in changes:
        spawn(companion_again(hub))


async def companion_again(hub):
    """The companion closed, then opened again on its (new) port when it is on and something is paired."""
    await hub.remote_off()
    await hub.remote_on()


def spawn(job):
    try:
        asyncio.get_running_loop().create_task(job)
    except RuntimeError:                          # no event loop (a test calling this directly): nothing to start
        job.close()
