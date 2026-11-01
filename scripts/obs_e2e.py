"""End-to-end check of CrossChat against a real OBS, without touching your own OBS or going live anywhere.

It sets up an OBS with its own settings: the CrossChat script loaded, obs-websocket on port 4456 and a stream that
goes to an RTMP receiver on this PC (ffmpeg). Then it checks that the script starts the hub, that the hub follows the
stream starting and stopping, that the overlay pages and the Theme API answer, and that the hub leaves when OBS closes.

  Windows: a portable OBS (the Windows .zip from github.com/obsproject/obs-studio/releases, extracted anywhere)
      python scripts/obs_e2e.py --obs C:\\path\\to\\OBS-Studio-33.0.1-Windows-x64 [--keep]
  Linux: the installed OBS (or --obs PATH, or --obs flatpak for OBS from Flathub, which needs this CrossChat in your
  home folder, where OBS's sandbox can see it). Its settings go to a throwaway folder (XDG_CONFIG_HOME), never
  ~/.config/obs-studio. Without a desktop (DISPLAY unset) it runs OBS on an Xvfb display of its own.
      python scripts/obs_e2e.py [--obs /usr/bin/obs | --obs flatpak] [--keep]

--keep leaves OBS and the hub running at the end (for screenshots). Needs ffmpeg on PATH, and requests and
websockets (hub/requirements.txt); on Linux without a desktop, Xvfb too.
"""
import argparse
import json
import os
import queue
import re
import shutil
import signal
import socket
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


def obs_settings(config, version, backdrop=None, script=None):
    """A fresh OBS profile and scene collection: a background (colour, or the picture `backdrop`), the four CrossChat
    widgets, the script (with `script` as its settings)."""
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
        "modules": {"scripts-tool": [{"path": os.path.join(ROOT, "obs", "crosschat.lua").replace("\\", "/"), "settings": script or {}}]}},
        indent=1))


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


def listening(port):
    """True when something on this computer accepts connections on `port`."""
    with socket.socket() as s:
        s.settimeout(2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def obs_answers():
    """True when obs-websocket says hello on its port and takes the password."""
    try:
        ws, _ = obs_connect()
        ws.close()
        return True
    except Exception:                        # refused, not ready yet, closed: not answering
        return False


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


# ---- each system's OBS: where it is, where its settings go, how it starts and how it's closed ----------------------
# Each returns a dict: "where" and "version" (to show), "config" (a fresh OBS settings folder), "command", "cwd",
# "env" (added to this environment; None removes a variable), "script" (the CrossChat script's settings), "close"
# (close OBS the normal way) and "cleanup"; or None when there's no OBS to test.
def windows_obs(args, home):
    """Windows: a portable OBS (the extracted .zip), which keeps its settings in a config folder of its own."""
    exe = os.path.join(args.obs or "", "bin", "64bit", "obs64.exe")
    if not check(os.path.isfile(exe), "portable OBS found", exe):
        return None
    version = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-Item '%s').VersionInfo.ProductVersion" % exe],
                             capture_output=True, text=True).stdout.strip()
    shutil.rmtree(os.path.join(args.obs, "config"), ignore_errors=True)
    return {"where": args.obs, "version": version, "config": os.path.join(args.obs, "config", "obs-studio"),
            "command": [exe, "--portable", "--multi", "--disable-updater", "--disable-shutdown-check", "--disable-missing-files-check"],
            "cwd": os.path.dirname(exe), "env": {}, "script": {},
            "close": lambda obs: subprocess.run(["taskkill", "/PID", str(obs.pid)], capture_output=True),   # as from the window's X
            "cleanup": lambda: None}


FLATPAK_OBS = "com.obsproject.Studio"


def linux_obs(args, home):
    """Linux: the installed OBS (or --obs PATH, or --obs flatpak for OBS from Flathub). XDG_CONFIG_HOME points it, and
    the CrossChat script, which looks where OBS does, at a throwaway settings folder, so ~/.config/obs-studio (or the
    Flatpak's own) is never read or written. Without a desktop it gets an Xvfb display of its own."""
    flatpak = args.obs == "flatpak"
    yours = None
    if flatpak:
        said = subprocess.run(["flatpak", "info", FLATPAK_OBS], capture_output=True, text=True, timeout=60).stdout if shutil.which("flatpak") else ""
        if not check("Version:" in said, "OBS from Flathub found", "flatpak info %s found nothing" % FLATPAK_OBS):
            return None
        # its sandbox has a /tmp of its own but sees your home folder, so the script must be there
        if not check(ROOT.startswith(os.path.expanduser("~") + os.sep), "this CrossChat is where OBS's sandbox can see it", ROOT):
            return None
        # and Flatpak always gives OBS its own settings folder: yours waits next to the test's home and comes back after
        config = os.path.expanduser("~/.var/app/%s/config/obs-studio" % FLATPAK_OBS)
        if os.path.exists(config):
            yours = os.path.join(home, "your-flatpak-obs-settings")
            shutil.move(config, yours)
            print("Your OBS (Flathub) settings wait in %s and are put back at the end." % yours)
        exe = "flatpak run " + FLATPAK_OBS
        env = {}
    else:
        exe = shutil.which(args.obs or "obs")
        if not check(bool(exe), "OBS found", args.obs or "no obs on PATH (pass --obs)"):
            return None
        said = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout
        config = os.path.join(home, "xdg-config", "obs-studio")
        env = {"XDG_CONFIG_HOME": os.path.dirname(config)}
    found = re.search(r"\d+\.\d+\.\d+", said)
    screen = None
    if not os.environ.get("DISPLAY"):
        screen = linux_xvfb()
        if not check(bool(screen), "an Xvfb display for OBS", "no desktop here, and Xvfb isn't installed or didn't start"):
            return None
        env.update(DISPLAY=screen[1], WAYLAND_DISPLAY=None, QT_QPA_PLATFORM="xcb")
    mine = os.path.join(ROOT, ".venv", "bin", "python3")      # where the script looks first, as after scripts/install.sh
    flags = ["--multi", "--disable-shutdown-check", "--disable-missing-files-check"]
    if flatpak:
        command = ["flatpak", "run", "--env=CROSSCHAT_CONFIG=" + os.path.join(home, "config.json"), FLATPAK_OBS, *flags]
    else:
        command = [exe, *flags]

    def close(obs):                                           # OBS on Linux closes normally on Ctrl+C
        if flatpak:
            os.kill(linux_flatpak_obs() or obs.pid, signal.SIGINT)
        else:
            obs.send_signal(signal.SIGINT)

    def cleanup():
        if screen:
            screen[0].terminate()
            screen[0].wait(10)
        if flatpak:
            shutil.rmtree(config, ignore_errors=True)
            if yours:
                shutil.move(yours, config)

    return {"where": exe + (" on Xvfb %s" % screen[1] if screen else ""), "version": found.group(0) if found else "30.0.0",
            "config": config, "command": command, "cwd": home, "env": env,
            "script": {} if os.path.exists(mine) else {"python": sys.executable}, "close": close, "cleanup": cleanup,
            "display": screen[1] if screen else os.environ.get("DISPLAY")}


def linux_flatpak_obs():
    """The process id, on this computer, of OBS in its Flatpak sandbox (the child of the sandbox's first process)."""
    listed = subprocess.run(["flatpak", "ps", "--columns=child-pid,application"], capture_output=True, text=True).stdout.split()
    starts = {listed[i] for i in range(0, len(listed) - 1, 2) if listed[i + 1] == FLATPAK_OBS}
    for entry in os.listdir("/proc"):
        try:
            with open("/proc/%s/stat" % entry, encoding="utf-8", errors="replace") as f:
                head, rest = f.read().rsplit(")", 1)
        except (OSError, ValueError):
            continue
        if rest.split()[1] in starts and head.endswith("(obs"):
            return int(entry)
    return None


def linux_xvfb():
    """(process, ":n") for a new 1920x1080 Xvfb display, or None."""
    if not shutil.which("Xvfb"):
        return None
    for n in range(90, 130):
        if os.path.exists("/tmp/.X%d-lock" % n) or os.path.exists("/tmp/.X11-unix/X%d" % n):
            continue
        screen = subprocess.Popen(["Xvfb", ":%d" % n, "-screen", "0", "1920x1080x24", "-nolisten", "tcp"], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if wait_for(lambda n=n, screen=screen: os.path.exists("/tmp/.X11-unix/X%d" % n) or screen.poll() is not None, 10, 0.1) \
                and screen.poll() is None:
            return screen, ":%d" % n
        screen.kill()
    return None


def obs_log(config):
    """The CrossChat script's lines in OBS's newest log."""
    try:
        folder = os.path.join(config, "logs")
        newest = max((os.path.join(folder, f) for f in os.listdir(folder)), key=os.path.getmtime)
        with open(newest, encoding="utf-8", errors="replace") as f:
            return [line.rstrip() for line in f if "crosschat" in line.lower()]
    except (OSError, ValueError):
        return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--obs", help="Windows: the folder of a portable OBS (the extracted .zip). Linux: the obs program (default: obs)")
    parser.add_argument("--keep", action="store_true", help="leave OBS and the hub running at the end")
    parser.add_argument("--backdrop", help="a 1920x1080 picture behind the widgets (for screenshots)")
    args = parser.parse_args()
    if hub_up():
        check(False, "port %d is free" % HUB_PORT, "something already answers there")
        return 1
    home = tempfile.mkdtemp(prefix="crosschat-e2e-")
    setup = (linux_obs if sys.platform.startswith("linux") else windows_obs)(args, home)
    if not setup:
        shutil.rmtree(home, ignore_errors=True)
        return 1
    print("OBS %s at %s" % (setup["version"], setup["where"]))

    config = setup["config"]
    obs_settings(config, setup["version"], args.backdrop, setup["script"])
    write(os.path.join(home, "config.json"), json.dumps({"port": HUB_PORT, "open_window_on_stream_start": False,
                                                         "x": {"enabled": True, "auto_go_live": False}}))
    receiver = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-listen", "1", "-i",
                                 "rtmp://127.0.0.1:1935/live/e2e", "-f", "null", "-"], stdin=subprocess.DEVNULL)
    env = {**os.environ, **setup["env"], "CROSSCHAT_CONFIG": os.path.join(home, "config.json")}
    obs = subprocess.Popen(setup["command"], cwd=setup["cwd"], env={k: v for k, v in env.items() if v is not None})
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
            print("OBS and the hub are still running (--keep%s). Close OBS when you are done."
                  % (", display %s" % setup["display"] if setup.get("display") else ""))
            return 0 if not failures else 1
        setup["close"](obs)                                          # a normal close
        obs.wait(30)
        check(not listening(WS_PORT), "OBS's WebSocket port %d is free right after OBS closes" % WS_PORT,
              "something still accepts connections there (the hub holding OBS's socket?)")
        check(bool(wait_for(lambda: not hub_up(), 30, 0.5)), "hub leaves when OBS closes")
        time.sleep(3)                                                # OBS started again a moment later
        obs = subprocess.Popen(setup["command"], cwd=setup["cwd"], env={k: v for k, v in env.items() if v is not None})
        again = wait_for(obs_answers, 60, 0.5)
        check(bool(again), "an OBS started again 3 s later has its WebSocket server", "no obs-websocket Hello on port %d" % WS_PORT)
        check(bool(wait_for(hub_up, 60, 0.5)), "and its script starts the hub again")
        setup["close"](obs)
        obs.wait(30)
        check(bool(wait_for(lambda: not hub_up(), 30, 0.5)), "that hub leaves with OBS too")
        for line in obs_log(config):                                # (what the script said, for the record)
            print("  OBS log: " + line)
    finally:
        if not args.keep:
            if obs.poll() is None:
                obs.kill()
            receiver.kill()
            requests.post(BASE + "/themes/delete", json={"name": "e2e-theme"}, timeout=2, headers={"Origin": BASE}) if hub_up() else None
            setup["cleanup"]()
            shutil.rmtree(home, ignore_errors=True)
    print("\n%d failed" % len(failures) if failures else "\nall passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
