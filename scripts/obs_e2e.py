"""End-to-end check of CrossChat against a real OBS, without touching your own OBS or going live anywhere.

It sets up an OBS with its own settings: the CrossChat script loaded, obs-websocket on port 4456, the chat window
docked as a Custom Browser Dock, and a stream that goes to an RTMP receiver on this PC (ffmpeg). Then it checks that
the script starts the hub, that the hub follows the stream starting and stopping, that the overlay pages and the
Theme API answer, and that the hub leaves when OBS closes.

  Windows: a portable OBS (the .zip from github.com/obsproject/obs-studio/releases, extracted anywhere)
    python scripts/obs_e2e.py --obs C:\\path\\to\\OBS-Studio-33.0.1-Windows-x64 [--keep]
  macOS: the installed OBS.app (/Applications/OBS.app unless --obs names another). OBS for Mac has no portable mode,
    so it runs with a stand-in home folder of its own; your OBS settings in ~/Library/Application Support/obs-studio
    are never read or changed. Run it from a Terminal on the Mac, or over SSH while someone is logged in at the Mac.
    python3 scripts/obs_e2e.py [--obs /Applications/OBS.app] [--crosschat "~/Library/Application Support/CrossChat"]
  Linux: the installed obs (or --obs PATH), with its settings in a throwaway folder (XDG_CONFIG_HOME), so
    ~/.config/obs-studio is never read or changed; or --obs flatpak for OBS from Flathub, which always uses its own
    settings folder: yours waits next to the test and is put back at the end, and the CrossChat folder must be in your
    home folder, where OBS's sandbox can see it. Without a desktop (no DISPLAY) OBS runs on an Xvfb display of its own.
    python3 scripts/obs_e2e.py [--obs /usr/bin/obs | --obs flatpak] [--crosschat ~/.local/share/CrossChat]

--crosschat tests another CrossChat folder (an installed copy) instead of this checkout. The OBS script there uses
that folder's own Python (python\\pythonw.exe or .venv on Windows, .venv/bin/python3 on a Mac or Linux), as it would for
a streamer. --keep leaves OBS and the hub running at the end (for screenshots). Needs ffmpeg (on PATH, or --ffmpeg),
and requests and websockets (hub/requirements.txt); on Linux without a desktop, Xvfb.
"""
import argparse
import glob
import json
import os
import plistlib
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
SCRIPT = os.path.join(ROOT, "obs", "crosschat.lua")
HUB_PORT, WS_PORT, WS_PASSWORD = 4486, 4456, "crosschat-e2e"
DEVTOOLS_PORT = 4496                         # OBS's own browser (its browser sources and docks) answers DevTools here, for the test only
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


def obs_settings(config, version, backdrop=None, script=SCRIPT):
    """A fresh OBS profile and scene collection: a background (colour, or the picture `backdrop`), the four CrossChat
    widgets, the script (`script`)."""
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
        "modules": {"scripts-tool": [{"path": script.replace("\\", "/"), "settings": {}}]}}, indent=1))


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


def obs_pages():
    """The pages OBS's own browser has open (browser sources and docks), from its DevTools list."""
    try:
        return requests.get("http://127.0.0.1:%d/json/list" % DEVTOOLS_PORT, timeout=3).json()
    except (requests.RequestException, ValueError):
        return []


def in_page(page, expression):
    """The value of a JavaScript `expression` in one of OBS's browser pages, or None."""
    try:
        with connect(page["webSocketDebuggerUrl"], open_timeout=5, max_size=None) as ws:
            ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expression, "returnByValue": True}}))
            while True:
                answer = json.loads(ws.recv(timeout=10))
                if answer.get("id") == 1:
                    return ((answer.get("result") or {}).get("result") or {}).get("value")
    except Exception:                        # (the page went away, or OBS's browser isn't answering)
        return None


def dock_page():
    """The CrossChat window docked in OBS (Docks → Custom Browser Docks), once it shows the chat."""
    for page in obs_pages():
        if page.get("type") == "page" and page.get("url", "").rstrip("/") == BASE and in_page(page, "document.title") == "CrossChat · chat":
            return page
    return None


def nobody_listens(port):
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) != 0


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


FLAGS = ["--multi", "--disable-updater", "--disable-shutdown-check", "--disable-missing-files-check",
         "--remote-debugging-port=%d" % DEVTOOLS_PORT]                # (OBS hands its command line to its browser)


# ---- Windows: a portable OBS, its settings in its own config folder ------------------------------------------------
def windows_obs(folder):
    """The portable OBS in `folder` (the extracted .zip): (program, version), or None."""
    exe = os.path.join(folder, "bin", "64bit", "obs64.exe")
    if not check(os.path.isfile(exe), "portable OBS found", exe):
        return None
    version = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-Item '%s').VersionInfo.ProductVersion" % exe],
                             capture_output=True, text=True).stdout.strip()
    return exe, version


def windows_settings(folder):
    """Portable OBS keeps its settings in config\\obs-studio next to its bin folder: start that afresh."""
    shutil.rmtree(os.path.join(folder, "config"), ignore_errors=True)
    return os.path.join(folder, "config", "obs-studio"), ["--portable"], {}


def windows_close(obs):
    subprocess.run(["taskkill", "/PID", str(obs.pid)], capture_output=True)    # a normal close, as from the window's X


# ---- macOS: the installed OBS.app with a stand-in home folder -------------------------------------------------------
MAC_OBS = "/Applications/OBS.app"


def mac_obs(app):
    """OBS.app at `app`: (program, version), or None."""
    exe = os.path.join(app, "Contents", "MacOS", "OBS")
    if not check(os.path.isfile(exe), "OBS.app found", exe):
        return None
    with open(os.path.join(app, "Contents", "Info.plist"), "rb") as f:
        version = plistlib.load(f)["CFBundleShortVersionString"]
    return exe, version


def mac_settings(home):
    """OBS for Mac has no portable mode: it keeps its settings in Application Support, wherever Foundation says the home
    folder is. CFFIXED_USER_HOME moves that (and OBS's preferences) to `home`, and HOME tells the CrossChat script the
    same, so this OBS never sees the Mac's own OBS settings. Only OBS's own plugins load: a third-party one that fails
    to load (an old Stream Deck plugin in /Library/Application Support/obs-studio, say) makes OBS open a dialog at
    the start that it won't quit past. (settings folder, extra flags, extra environment)"""
    return (os.path.join(home, "Library", "Application Support", "obs-studio"), ["--only-bundled-plugins"],
            {"HOME": home, "CFFIXED_USER_HOME": home})


def mac_first_start(config):
    """No questions at the first start: OBS for Mac otherwise opens its permissions window (screen recording, camera,
    microphone, input monitoring) and waits there until someone closes it."""
    path = os.path.join(config, "global.ini")
    with open(path, encoding="utf-8") as f:
        ini = f.read()
    write(path, ini.replace("[General]\n", "[General]\nMacOSPermissionsDialogLastShown=1\n", 1))


def mac_hub_python(home, crosschat):
    """Did the OBS script start the hub with the Python environment the installer makes (<CrossChat>/.venv)? The hub's
    log says which one runs it (`ps` can't: a framework Python starts its real program under another name)."""
    try:
        with open(os.path.join(home, "crosschat.log"), encoding="utf-8") as f:
            started = [line for line in f if " on http://127.0.0.1:%d " % HUB_PORT in line]
    except OSError:
        started = []
    where = started[-1].rsplit(" in ", 1)[-1].strip().rstrip(")") if started else "no start line in crosschat.log"
    venv = os.path.join(crosschat, ".venv")
    check(os.path.isdir(venv) and os.path.realpath(where) == os.path.realpath(venv), "the OBS script runs the hub with CrossChat's own Python (.venv)",
          where)


def mac_close(obs):
    """Quit OBS cleanly, as from its menu: OBS for Mac shuts down properly on SIGTERM."""
    obs.send_signal(signal.SIGTERM)


# ---- Linux: the installed OBS, or OBS from Flathub ------------------------------------------------------------------
FLATPAK = "com.obsproject.Studio"
FLATPAK_SETTINGS = os.path.expanduser("~/.var/app/%s/config/obs-studio" % FLATPAK)


def linux_obs(program):
    """The obs program (`program`, else obs on PATH), or "flatpak" for OBS from Flathub: (program, version), or None."""
    if program == "flatpak":
        said = subprocess.run(["flatpak", "info", FLATPAK], capture_output=True, text=True).stdout if shutil.which("flatpak") else ""
        found = re.search(r"Version:\s*(\d+\.\d+\.\d+)", said)
        if not check(bool(found), "OBS from Flathub found", "flatpak info %s found nothing" % FLATPAK):
            return None
        return shutil.which("flatpak"), found.group(1)
    exe = shutil.which(program or "obs")
    if not check(bool(exe), "OBS found", program or "no obs on PATH (pass --obs)"):
        return None
    found = re.search(r"\d+\.\d+\.\d+", subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout)
    return exe, found.group(0) if found else "30.0.0"


def linux_has_browser(flatpak):
    """Whether this OBS has its Browser Source (Ubuntu's and Debian's own obs-studio package leaves it out)."""
    return flatpak or bool(glob.glob("/usr/lib*/obs-plugins/obs-browser.so") + glob.glob("/usr/lib/*/obs-plugins/obs-browser.so")
                           + glob.glob("/usr/local/lib*/obs-plugins/obs-browser.so"))


def linux_settings(home, flatpak, crosschat):
    """(settings folder, extra arguments, extra environment). The installed OBS, and the CrossChat script (which looks
    where OBS does), get XDG_CONFIG_HOME in `home`. OBS from Flathub always uses its own folder: whatever is there
    waits in `home` until linux_restore. Without a desktop, OBS gets an Xvfb display of its own."""
    env = {}
    if not os.environ.get("DISPLAY"):
        screen = linux_xvfb()
        if not check(bool(screen), "an Xvfb display for OBS", "no desktop here, and Xvfb isn't installed or didn't start"):
            return None
        env.update(DISPLAY=screen, WAYLAND_DISPLAY=None, QT_QPA_PLATFORM="xcb")
    if not flatpak:
        config = os.path.join(home, "xdg-config", "obs-studio")
        env["XDG_CONFIG_HOME"] = os.path.dirname(config)
        return config, [], env
    # the sandbox has a /tmp of its own but sees the home folder: the CrossChat script must be there
    if not check(crosschat.startswith(os.path.expanduser("~") + os.sep), "this CrossChat is where OBS's sandbox can see it", crosschat):
        return None
    if os.path.exists(FLATPAK_SETTINGS):
        shutil.move(FLATPAK_SETTINGS, os.path.join(home, "your-flatpak-obs-settings"))
        print("Your OBS (Flathub) settings wait in %s and are put back at the end." % os.path.join(home, "your-flatpak-obs-settings"))
    return FLATPAK_SETTINGS, ["run", "--env=CROSSCHAT_CONFIG=" + os.path.join(home, "config.json"), FLATPAK], env


def linux_restore(home):
    """OBS from Flathub: this test's settings go next to its log in `home`, and yours come back."""
    if os.path.exists(FLATPAK_SETTINGS):
        shutil.move(FLATPAK_SETTINGS, os.path.join(home, "test-flatpak-obs-settings"))
    if os.path.exists(os.path.join(home, "your-flatpak-obs-settings")):
        shutil.move(os.path.join(home, "your-flatpak-obs-settings"), FLATPAK_SETTINGS)


LINUX_SCREENS = []                           # the Xvfb displays started here, stopped at the end


def linux_xvfb():
    """The name (":n") of a new 1920x1080 Xvfb display, or None."""
    if not shutil.which("Xvfb"):
        return None
    for n in range(90, 130):
        if os.path.exists("/tmp/.X%d-lock" % n) or os.path.exists("/tmp/.X11-unix/X%d" % n):
            continue
        screen = subprocess.Popen(["Xvfb", ":%d" % n, "-screen", "0", "1920x1080x24", "-nolisten", "tcp"], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if wait_for(lambda n=n, screen=screen: os.path.exists("/tmp/.X11-unix/X%d" % n) or screen.poll() is not None, 10, 0.1) \
                and screen.poll() is None:
            LINUX_SCREENS.append(screen)
            return ":%d" % n
        screen.kill()
    return None


def linux_close(obs, flatpak):
    """Close OBS normally: OBS on Linux does on Ctrl+C (SIGINT). In the Flatpak, that goes to OBS itself, the child of
    the sandbox's first process (flatpak ps names it), not to `flatpak run`."""
    pid = obs.pid
    if flatpak:
        listed = subprocess.run(["flatpak", "ps", "--columns=child-pid,application"], capture_output=True, text=True).stdout.split()
        starts = {listed[i] for i in range(0, len(listed) - 1, 2) if listed[i + 1] == FLATPAK}
        for entry in os.listdir("/proc"):
            try:
                with open("/proc/%s/stat" % entry, encoding="utf-8", errors="replace") as f:
                    head, rest = f.read().rsplit(")", 1)
            except (OSError, ValueError):
                continue
            if rest.split()[1] in starts and head.endswith("(obs"):
                pid = int(entry)
    os.kill(pid, signal.SIGINT)


def obs_log(config):
    """The CrossChat script's lines in OBS's newest log."""
    try:
        folder = os.path.join(config, "logs")
        newest = max((os.path.join(folder, f) for f in os.listdir(folder)), key=os.path.getmtime)
        with open(newest, encoding="utf-8", errors="replace") as f:
            return [line.rstrip() for line in f if "crosschat" in line.lower()]
    except (OSError, ValueError):
        return []


def obs_answers():
    """True when obs-websocket says hello on its port and takes the password."""
    try:
        ws, _ = obs_connect()
        ws.close()
        return True
    except Exception:                        # refused, not ready yet, closed: not answering
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--obs", help="Windows: the folder of a portable OBS (the extracted .zip). macOS: OBS.app (default %s). "
                                      "Linux: the obs program (default: obs on PATH), or flatpak for OBS from Flathub" % MAC_OBS)
    parser.add_argument("--crosschat", default=ROOT, help="the CrossChat folder to test, such as an installed copy (default: this checkout)")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="the ffmpeg program for the RTMP receiver (default: ffmpeg on PATH)")
    parser.add_argument("--keep", action="store_true", help="leave OBS and the hub running at the end")
    parser.add_argument("--backdrop", help="a 1920x1080 picture behind the widgets (for screenshots)")
    args = parser.parse_args()
    mac = sys.platform == "darwin"
    linux = sys.platform.startswith("linux")
    flatpak = linux and args.obs == "flatpak"
    crosschat = os.path.abspath(os.path.expanduser(args.crosschat))
    if not (mac or linux) and not args.obs:
        parser.error("--obs: the folder of a portable OBS")
    found = mac_obs(os.path.expanduser(args.obs or MAC_OBS)) if mac else linux_obs(args.obs) if linux else windows_obs(args.obs)
    if not found:
        return 1
    exe, version = found
    print("OBS %s at %s" % (version, FLATPAK + " (Flathub)" if flatpak else exe))
    if hub_up():
        check(False, "port %d is free" % HUB_PORT, "something already answers there")
        return 1

    home = tempfile.mkdtemp(prefix="crosschat-e2e-")
    if mac:
        settings = mac_settings(os.path.join(home, "home"))
    elif linux:
        settings = linux_settings(home, flatpak, crosschat)
    else:
        settings = windows_settings(args.obs)
    if not settings:
        shutil.rmtree(home, ignore_errors=True)
        return 1
    config, flags, extra_env = settings
    browser = linux_has_browser(flatpak) if linux else True         # (Ubuntu's own OBS has no Browser Source)
    obs_settings(config, version, args.backdrop, os.path.join(crosschat, "obs", "crosschat.lua"))
    if mac:
        mac_first_start(config)
    write(os.path.join(home, "config.json"), json.dumps({"port": HUB_PORT, "open_window_on_stream_start": False,
                                                         "x": {"enabled": True, "auto_go_live": False}}))
    receiver = subprocess.Popen([args.ffmpeg, "-hide_banner", "-loglevel", "error", "-listen", "1", "-i",
                                 "rtmp://127.0.0.1:1935/live/e2e", "-f", "null", "-"], stdin=subprocess.DEVNULL)
    env = {k: v for k, v in {**os.environ, "CROSSCHAT_CONFIG": os.path.join(home, "config.json"), **extra_env}.items() if v is not None}

    def start_obs():
        return subprocess.Popen([exe, *flags, *FLAGS], cwd=os.path.dirname(exe), env=env)

    def close_obs(running):
        if mac:
            mac_close(running)
        elif linux:
            linux_close(running, flatpak)
        else:
            windows_close(running)

    obs = start_obs()
    try:
        about = wait_for(hub_up, 60, 0.5)
        check(bool(about), "the OBS script started the hub", "nothing on port %d after 60 s" % HUB_PORT)
        if not about:
            return 1
        if mac:
            mac_hub_python(home, crosschat)
        events = queue.Queue()
        threading.Thread(target=listen, args=(events,), daemon=True).start()
        check(bool(expect(events, lambda e: e["type"] == "status" and not e["live"], 10)), "hub reports OFF AIR before streaming")

        for widget in ("chat", "featured", "viewers", "alerts"):
            r = requests.get("%s/overlay/%s" % (BASE, widget), timeout=5)
            check(r.status_code == 200 and "<html" in r.text.lower(), "overlay page /overlay/%s" % widget, r.status_code)
        dock = None
        if browser:
            shown = wait_for(lambda: {p["url"].split("/overlay/")[1].split("?")[0] for p in obs_pages() if "/overlay/" in p.get("url", "")}
                             >= {"chat", "featured", "viewers", "alerts"}, 30, 0.5)
            check(bool(shown), "OBS's browser sources show the four widgets", [p.get("url") for p in obs_pages()])
            if linux:                        # (seen with OBS 33.0.1 from Flathub: its window is there, unmapped, and no page loads)
                print("SKIP  the chat window docked in OBS: on Linux the dock this test writes into OBS's settings stays hidden")
            else:
                dock = wait_for(dock_page, 30, 0.5)
                check(bool(dock), "the chat window is docked in OBS (Custom Browser Dock)", [p.get("url") for p in obs_pages()])
        else:
            print("SKIP  OBS's browser sources and the docked chat window: this OBS has no Browser Source")
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
        if line and dock:
            seen = wait_for(lambda: in_page(dock, "document.body.innerText.includes(%s)" % json.dumps(line["text"])), 10, 0.5)
            check(bool(seen), "test chat shows in the OBS dock", line["text"])
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
                  % (", on display " + env["DISPLAY"] if LINUX_SCREENS else ""))
            return 0 if not failures else 1
        close_obs(obs)
        obs.wait(30)
        # (the hub mustn't hold on to anything of OBS's: a restarted OBS needs its WebSocket port back at once)
        check(bool(wait_for(lambda: nobody_listens(WS_PORT), 3, 0.25)), "OBS's WebSocket port is free once OBS has closed")
        check(bool(wait_for(lambda: not hub_up(), 30, 0.5)), "hub leaves when OBS closes")
        said = obs_log(config)
        time.sleep(3)                                                # OBS started again a moment later
        obs = start_obs()
        check(bool(wait_for(obs_answers, 60, 0.5)), "an OBS started again 3 s later has its WebSocket server", "no Hello on port %d" % WS_PORT)
        check(bool(wait_for(hub_up, 60, 0.5)), "and its script starts the hub again", "nothing on port %d" % HUB_PORT)
        close_obs(obs)
        obs.wait(30)
        check(bool(wait_for(lambda: not hub_up(), 30, 0.5)), "that hub leaves with OBS too")
        for text in said:                                            # what the script said in the first OBS, for the record
            print("  OBS log: " + text)
    finally:
        if not args.keep:
            if obs.poll() is None:
                obs.kill()
            receiver.kill()
            requests.post(BASE + "/themes/delete", json={"name": "e2e-theme"}, timeout=2, headers={"Origin": BASE}) if hub_up() else None
            if flatpak:
                linux_restore(home)
            for screen in LINUX_SCREENS:
                screen.terminate()
            if failures or sys.exc_info()[0]:
                print("The hub's log (crosschat.log) and OBS's own settings and logs are kept in %s" % home)
            else:
                shutil.rmtree(home, ignore_errors=True)
    print("\n%d failed" % len(failures) if failures else "\nall passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
