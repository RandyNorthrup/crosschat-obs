"""Used by the installer: write config.json from the answers it collected, and switch on OBS's WebSocket server.

  python setup_config.py config TEMPLATE TARGET     answers in CROSSCHAT_* environment variables
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
    data["x"]["enabled"] = answer("X") == "1"
    data["x"]["auto_go_live"] = answer("X_AUTO") != "0"
    data["x"]["source"] = answer("X_SOURCE") or data["x"]["source"]
    data["x"]["title"] = answer("X_TITLE") or data["x"]["title"]
    write(target, data)


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
    elif sys.argv[1:2] == ["websocket"] and len(sys.argv) == 3:
        websocket(sys.argv[2])
    else:
        sys.exit(__doc__)
