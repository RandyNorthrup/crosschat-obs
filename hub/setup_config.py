"""Used by the installers: write config.json, and switch on OBS's WebSocket server.

  python setup_config.py config TEMPLATE TARGET     answers in CROSSCHAT_* environment variables (Install.cmd)
  python setup_config.py ensure TEMPLATE TARGET     the template as it is, only when TARGET doesn't exist yet (setup.exe:
                                                    channels are set later in CrossChat's Settings)
  python setup_config.py websocket FILE             turn the server on (a password is made when it has none)
"""
import json
import os
import secrets
import sys


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(path + ".tmp", path)


def config(template, target):
    with open(template, encoding="utf-8-sig") as f:
        data = json.load(f)
    answer = lambda name: os.environ.get("CROSSCHAT_" + name, "").strip()   # noqa: E731
    for key in ("twitch", "youtube", "kick", "tiktok"):
        data[key] = answer(key.upper())
    data["facebook"] = answer("FACEBOOK") == "1"
    data["instagram"] = answer("INSTAGRAM") == "1"
    if answer("EMOTES") == "0":                 # the one outside service on by default; the installer asks
        data["emotes"] = {"bttv": False, "ffz": False, "7tv": False}
    data["updates"] = {"check": answer("UPDATES") == "1"}      # off unless the streamer said yes
    data["x"]["enabled"] = answer("X") == "1"
    data["x"]["auto_go_live"] = answer("X_AUTO") != "0"
    data["x"]["source"] = answer("X_SOURCE") or data["x"]["source"]
    data["x"]["title"] = answer("X_TITLE") or data["x"]["title"]
    write(target, data)


def ensure(template, target):
    if os.path.exists(target):
        return
    with open(template, encoding="utf-8-sig") as f:
        write(target, json.load(f))


def websocket(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"server_port": 4455, "auth_required": True, "alerts_enabled": False, "first_load": False}
    data["server_enabled"] = True
    if data.get("auth_required", True) and not data.get("server_password"):
        data["auth_required"] = True
        data["server_password"] = secrets.token_urlsafe(12)
    write(path, data)


if __name__ == "__main__":
    if sys.argv[1:2] == ["config"] and len(sys.argv) == 4:
        config(sys.argv[2], sys.argv[3])
    elif sys.argv[1:2] == ["ensure"] and len(sys.argv) == 4:
        ensure(sys.argv[2], sys.argv[3])
    elif sys.argv[1:2] == ["websocket"] and len(sys.argv) == 3:
        websocket(sys.argv[2])
    else:
        sys.exit(__doc__)
