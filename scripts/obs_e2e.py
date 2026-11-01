"""End-to-end check of CrossChat against a real OBS, without touching your own OBS or going live anywhere.

It sets up a portable OBS (the Windows .zip from github.com/obsproject/obs-studio/releases, extracted anywhere) with
its own settings: the CrossChat script loaded, obs-websocket on port 4456 and a stream that goes to an RTMP
receiver on this PC (ffmpeg). Then it checks that the script starts the hub, that the hub follows the stream
starting and stopping, that the overlay pages and the Theme API answer, and that the hub leaves when OBS closes.

  python scripts/obs_e2e.py --obs C:\\path\\to\\OBS-Studio-33.0.1-Windows-x64 [--keep]

--keep leaves OBS and the hub running at the end (for screenshots). Needs ffmpeg on PATH, and requests and
websockets (hub/requirements.txt).
"""
import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

import requests
from websockets.sync.client import connect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HUB_PORT, WS_PORT, WS_PASSWORD = 4486, 4456, "crosschat-e2e"
BASE = "http://127.0.0.1:%d" % HUB_PORT
failures = []


def check(ok, what, detail=""):
    print(("PASS  " if ok else "FAIL  ") + what + ("" if ok else "  (%s)" % detail))
    if not ok:
        failures.append(what)
    return ok


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def obs_settings(config, version, backdrop=None):
    """A fresh OBS profile and scene collection: a background (colour, or the picture `backdrop`), the four CrossChat
    widgets, the script."""
    major, minor, patch = (int(p) for p in version.split(".")[:3])
    ini = ("[General]\nFirstRun=true\nLastVersion=%d\nEnableAutoUpdates=false\n\n[Basic]\nProfile=CrossChat\nProfileDir=CrossChat\n"
           "SceneCollection=CrossChat\nSceneCollectionFile=CrossChat\n" % ((major << 24) | (minor << 16) | patch))
    # the CrossChat window docked inside OBS (Docks → Custom Browser Docks), as the README tells streamers to set it up
    ini += "\n[BasicWindow]\nExtraBrowserDocks=%s\n" % json.dumps([{"title": "CrossChat", "url": BASE + "/", "uuid": str(uuid.uuid4())}])
    write(os.path.join(config, "global.ini"), ini)
    write(os.path.join(config, "user.ini"), ini)
    write(os.path.join(config, "plugin_config", "obs-websocket", "config.json"), json.dumps(
        {"alerts_enabled": False, "auth_required": True, "first_load": False, "server_enabled": True,
         "server_password": WS_PASSWORD, "server_port": WS_PORT}))
    profile = os.path.join(config, "basic", "profiles", "CrossChat")
    write(os.path.join(profile, "basic.ini"), "[General]\nName=CrossChat\n\n[Video]\nBaseCX=1920\nBaseCY=1080\nOutputCX=1280\n"
          "OutputCY=720\nFPSCommon=30\n\n[Output]\nMode=Simple\n\n[SimpleOutput]\nVBitrate=1500\nStreamEncoder=x264\n")
    write(os.path.join(profile, "service.json"), json.dumps(
        {"type": "rtmp_custom", "settings": {"server": "rtmp://127.0.0.1:1935/live", "key": "e2e", "use_auth": False}}))
    sources, items = [], []

    def add(kind, name, settings, x=0, y=0, versioned=None):
        sid = str(uuid.uuid4())
        sources.append({"id": kind, "versioned_id": versioned or kind, "name": name, "uuid": sid, "settings": settings})
        items.append({"name": name, "source_uuid": sid, "id": len(items) + 1, "visible": True, "locked": False,
                      "pos": {"x": x, "y": y}, "scale": {"x": 1.0, "y": 1.0}, "rot": 0.0, "align": 5, "bounds_type": 0})

    if backdrop:
        add("image_source", "Backdrop", {"file": os.path.abspath(backdrop).replace("\\", "/")})
    else:
        add("color_source", "Backdrop", {"color": 4281078297, "width": 1920, "height": 1080}, versioned="color_source_v3")
    for name, path, w, h, x, y in (("CrossChat chat", "chat", 450, 800, 1440, 230), ("CrossChat featured", "featured", 900, 260, 60, 790),
                                   ("CrossChat viewers", "viewers", 600, 120, 60, 40), ("CrossChat alerts", "alerts", 800, 300, 560, 120)):
        add("browser_source", name, {"url": "%s/overlay/%s?demo" % (BASE, path), "width": w, "height": h, "fps": 30, "shutdown": False}, x, y)
    scene_id = str(uuid.uuid4())
    sources.insert(0, {"id": "scene", "versioned_id": "scene", "name": "Main", "uuid": scene_id,
                       "settings": {"items": items, "id_counter": len(items), "custom_size": False}})
    write(os.path.join(config, "basic", "scenes", "CrossChat.json"), json.dumps({
        "name": "CrossChat", "current_scene": "Main", "current_program_scene": "Main", "scene_order": [{"name": "Main"}],
        "sources": sources, "groups": [], "transitions": [], "current_transition": "Fade", "transition_duration": 300,
        "modules": {"scripts-tool": [{"path": os.path.join(ROOT, "obs", "crosschat.lua").replace("\\", "/"), "settings": {}}]}}, indent=1))


def wait_for(test, seconds, step=0.25):
    end = time.time() + seconds
    while time.time() < end:
        result = test()
        if result:
            return result
        time.sleep(step)
    return None


def hub_up():
    try:
        return requests.get(BASE + "/version", timeout=2).json()
    except (requests.RequestException, ValueError):
        return None


def listen(events):
    """Every event the hub sends, into a queue."""
    with requests.get(BASE + "/events", stream=True, timeout=(5, 60)) as r:
        for line in r.iter_lines(chunk_size=1, decode_unicode=True):
            if line and line.startswith("data: "):
                events.put(json.loads(line[6:]))


def expect(events, test, seconds):
    end = time.time() + seconds
    while time.time() < end:
        try:
            event = events.get(timeout=max(0.1, end - time.time()))
        except queue.Empty:
            break
        if test(event):
            return event
    return None


def obs_request(ws, kind, data=None):
    rid = str(uuid.uuid4())
    ws.send(json.dumps({"op": 6, "d": {"requestType": kind, "requestId": rid, **({"requestData": data} if data else {})}}))
    while True:
        message = json.loads(ws.recv(timeout=20))
        if message["op"] == 7 and message["d"]["requestId"] == rid:
            return message["d"]


def obs_connect():
    import base64
    import hashlib
    ws = connect("ws://127.0.0.1:%d" % WS_PORT, open_timeout=5)
    hello = json.loads(ws.recv(timeout=10))["d"]
    auth = hello["authentication"]
    secret = base64.b64encode(hashlib.sha256((WS_PASSWORD + auth["salt"]).encode()).digest()).decode()
    ws.send(json.dumps({"op": 1, "d": {"rpcVersion": 1, "authentication": base64.b64encode(
        hashlib.sha256((secret + auth["challenge"]).encode()).digest()).decode(), "eventSubscriptions": 0}}))
    json.loads(ws.recv(timeout=10))
    return ws, hello


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--obs", required=True, help="folder of a portable OBS (the extracted Windows .zip)")
    parser.add_argument("--keep", action="store_true", help="leave OBS and the hub running at the end")
    parser.add_argument("--backdrop", help="a 1920x1080 picture behind the widgets (for screenshots)")
    args = parser.parse_args()
    exe = os.path.join(args.obs, "bin", "64bit", "obs64.exe")
    if not check(os.path.isfile(exe), "portable OBS found", exe):
        return 1
    version = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-Item '%s').VersionInfo.ProductVersion" % exe],
                             capture_output=True, text=True).stdout.strip()
    print("OBS %s at %s" % (version, args.obs))
    if hub_up():
        check(False, "port %d is free" % HUB_PORT, "something already answers there")
        return 1

    config = os.path.join(args.obs, "config", "obs-studio")
    shutil.rmtree(os.path.join(args.obs, "config"), ignore_errors=True)
    obs_settings(config, version, args.backdrop)
    home = tempfile.mkdtemp(prefix="crosschat-e2e-")
    write(os.path.join(home, "config.json"), json.dumps({"port": HUB_PORT, "open_window_on_stream_start": False,
                                                         "x": {"enabled": True, "auto_go_live": False}}))
    receiver = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-listen", "1", "-i",
                                 "rtmp://127.0.0.1:1935/live/e2e", "-f", "null", "-"], stdin=subprocess.DEVNULL)
    env = dict(os.environ, CROSSCHAT_CONFIG=os.path.join(home, "config.json"))
    obs = subprocess.Popen([exe, "--portable", "--multi", "--disable-updater", "--disable-shutdown-check", "--disable-missing-files-check"],
                           cwd=os.path.dirname(exe), env=env)
    try:
        about = wait_for(hub_up, 60, 0.5)
        check(bool(about), "the OBS script started the hub", "nothing on port %d after 60 s" % HUB_PORT)
        if not about:
            return 1
        events = queue.Queue()
        threading.Thread(target=listen, args=(events,), daemon=True).start()
        check(bool(expect(events, lambda e: e["type"] == "status" and not e["live"], 10)), "hub reports OFF AIR before streaming")

        for widget in ("chat", "featured", "viewers", "alerts"):
            r = requests.get("%s/overlay/%s" % (BASE, widget), timeout=5)
            check(r.status_code == 200 and "<html" in r.text.lower(), "overlay page /overlay/%s" % widget, r.status_code)
        themes = requests.get(BASE + "/themes", timeout=5).json()
        check(len([t for t in themes["themes"] if t["builtin"]]) >= 1, "built-in themes listed (%d)" % len(themes["themes"]))
        r = requests.post(BASE + "/themes/save", json={"name": "e2e-theme", "theme": {"schema": 1, "label": "E2E"}}, timeout=5,
                          headers={"Origin": BASE})
        check(r.json().get("ok"), "a theme saves", r.text)
        check(bool(expect(events, lambda e: e["type"] == "theme" and e["name"] == "e2e-theme", 5)), "saving a theme tells the overlays")
        r = requests.post(BASE + "/themes/save", json={"name": "e2e-theme", "theme": {}}, timeout=5, headers={"Origin": "https://evil.example"})
        check(r.status_code == 403, "another website can't change themes", r.status_code)

        ws, hello = obs_connect()
        print("obs-websocket %s, OBS %s" % (hello.get("obsWebSocketVersion"), hello.get("obsStudioVersion")))
        started = obs_request(ws, "StartStream")
        check(started["requestStatus"]["result"], "OBS starts streaming to the RTMP receiver", started["requestStatus"])
        live = expect(events, lambda e: e["type"] == "status" and e["live"], 30)
        check(bool(live), "hub sees the stream start (LIVE)")
        check(bool(expect(events, lambda e: e["type"] == "msg" and "this PC only" in e["text"], 5)),
              "a stream to this PC counts as a test (nothing public follows)")
        requests.post(BASE + "/test", json={"kind": "chat"}, timeout=5, headers={"Origin": BASE})
        line = expect(events, lambda e: e["type"] == "msg" and e.get("test") and e["kind"] == "chat", 10)
        check(bool(line), "test chat reaches the overlays")
        if line:
            requests.get(BASE + "/feature?id=" + line["id"], timeout=5)
            featured = expect(events, lambda e: e["type"] == "feature" and e["msg"], 5)
            check(bool(featured) and featured["msg"]["id"] == line["id"], "a message can be featured")
        time.sleep(3)
        stopped = obs_request(ws, "StopStream")
        check(stopped["requestStatus"]["result"], "OBS stops streaming", stopped["requestStatus"])
        check(bool(expect(events, lambda e: e["type"] == "status" and not e["live"], 30)), "hub sees the stream stop (OFF AIR)")
        ws.close()
        if args.keep:
            print("OBS and the hub are still running (--keep). Close OBS when you are done.")
            return 0 if not failures else 1
        subprocess.run(["taskkill", "/PID", str(obs.pid)], capture_output=True)    # a normal close, as from the window's X
        obs.wait(30)
        check(bool(wait_for(lambda: not hub_up(), 30, 0.5)), "hub leaves when OBS closes")
    finally:
        if not args.keep:
            if obs.poll() is None:
                obs.kill()
            receiver.kill()
            requests.post(BASE + "/themes/delete", json={"name": "e2e-theme"}, timeout=2, headers={"Origin": BASE}) if hub_up() else None
            shutil.rmtree(home, ignore_errors=True)
    print("\n%d failed" % len(failures) if failures else "\nall passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
