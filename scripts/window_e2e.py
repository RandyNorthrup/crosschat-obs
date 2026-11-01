"""Real check of CrossChat's windows with the CrossChat extension: a real browser, the hub, a stand-in for OBS.

It starts a browser of its own (a throwaway profile) with this checkout's extension loaded over DevTools
(Extensions.loadUnpacked: branded Chrome no longer takes --load-extension), runs this checkout's hub on 127.0.0.1:4466
with a stand-in for OBS (obs-websocket 5), and checks that:
  - when the stream starts, the hub opens the chat window and the TikTok LIVE page as --app windows, and the extension
    puts each where config.json says (a running browser opens a new window where it likes);
  - "Open chat" with another place in config.json moves the chat window there;
  - after the stream, the hub closes both through the extension;
  - your windows are left alone: an ordinary window with the chat in a tab, an ordinary window at the TikTok page's
    exact address, an --app window of another TikTok page and an --app window of the Theme Studio keep their place
    and stay open;
  - the system's own way (AppleScript, X11, Windows' user32) is never used: here it is a recorder.
Where the windows really are is asked of the desktop as well: macOS's window server (CGWindowList), the X server, or
KWin (through its scripting, on Wayland). Wayland lets no program place a window, the browser included: there the
position is reported, and the size and the closing are checked.

No page from the internet loads: the throwaway browser resolves no name but 127.0.0.1 (the TikTok page shows the
browser's own "can't be reached" page, at TikTok's address).

  python3 scripts/window_e2e.py [--browser PATH] [--wayland [--xwayland]] [--obs [OBS.app]] [--keep]

macOS: run it in a logged-in session (from Terminal, or over SSH while someone is logged in at the Mac). The browser
  uses a mock keychain, and the hub opens windows through a stand-in browser app in the test's folder (an .app, as the
  hub's "browser" setting takes), which is unregistered from Launch Services at the end.
  --obs: OBS itself starts the hub (OBS.app with a stand-in home folder and only its own plugins, as scripts/obs_e2e.py
  sets it up; your OBS settings are never read or changed), the case where macOS refuses AppleScript. Then the chat
  window opens with Open chat, X Live Studio's page with a dry run of Go live on X, "Open chat" after Settings' window
  position goes back to auto moves it, and quitting OBS closes both; it also checks the hub leaves once OBS has
  closed. It needs <this checkout>/.venv, the Python environment the OBS script runs the hub with.
Linux: it runs in a folder of its own: its own D-Bus session, runtime folder and home folder (nothing reaches your
  desktop session or keyring), on an Xvfb display of its own; --wayland on KWin's virtual screen (kwin_wayland
  --virtual) instead, with the browser as a Wayland program, or with --xwayland through KWin's XWayland.
Windows: not supported (the browser's DevTools pipe is file descriptors 3 and 4, which Windows has no plain way to
  pass on).
Needs requests and websockets (hub/requirements.txt) and port 4466 free; on Linux, Xvfb (or kwin_wayland) and
dbus-run-session. --keep leaves the test folder (its crosschat.log and browser log) for a look.
"""
import argparse
import asyncio
import faulthandler
import json
import os
import plistlib
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTENSION = os.path.join(ROOT, "extension")
PORT = 4466                                  # the extension talks to the hub on this port only
CHAT = "http://127.0.0.1:%d/" % PORT
TIKTOK = "https://www.tiktok.com/@crosschat_e2e/live"
CHAT_BOX, TIKTOK_BOX, X_BOX, MOVED_BOX = (40, 80, 420, 560), (480, 80, 380, 320), (480, 420, 380, 300), (100, 140, 460, 600)
MAC, LINUX = sys.platform == "darwin", sys.platform.startswith("linux")
LSREGISTER = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
failures = []


def check(ok, what, detail=""):
    print(("PASS  " if ok else "FAIL  ") + what + ("" if ok or not detail else "  (%s)" % detail), flush=True)
    if not ok:
        failures.append(what)
    return ok


def rect(box, names=("x", "y", "width", "height")):
    return dict(zip(names, box, strict=True))


def info(what):
    print("INFO  " + what, flush=True)


# ---- the browser's DevTools, over a pipe ---------------------------------------------------------------------------
class DevTools:
    """A browser started with --remote-debugging-pipe: DevTools commands go in on its file descriptor 3, answers come
    out of its 4, as JSON separated by NUL bytes."""

    def __init__(self, command, log_path):
        import fcntl
        theirs_in, mine_out = os.pipe()
        mine_in, theirs_out = os.pipe()
        high = [fcntl.fcntl(fd, fcntl.F_DUPFD, 10) for fd in (theirs_in, theirs_out)]   # (clear of 3 and 4)
        os.close(theirs_in)
        os.close(theirs_out)
        a, b = high
        shell = 'exec "$@" 3<&%d 4>&%d %d<&- %d>&-' % (a, b, a, b)
        self.log = open(log_path, "wb")
        self.proc = subprocess.Popen(["bash", "-c", shell, "browser"] + command, pass_fds=(a, b), stdin=subprocess.DEVNULL,
                                     stdout=self.log, stderr=self.log, start_new_session=True)
        os.close(a)
        os.close(b)
        self.out = os.fdopen(mine_out, "wb", buffering=0)
        self.inp = os.fdopen(mine_in, "rb", buffering=0)
        self.n, self.answers, self.lock = 0, {}, threading.Condition()
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        buf = b""
        while True:
            chunk = self.inp.read(1 << 16)
            if not chunk:
                return
            buf += chunk
            while b"\0" in buf:
                raw, buf = buf.split(b"\0", 1)
                message = json.loads(raw)
                if "id" in message:
                    with self.lock:
                        self.answers[message["id"]] = message
                        self.lock.notify_all()

    def call(self, method, params=None, session=None, timeout=30):
        with self.lock:
            self.n += 1
            n = self.n
        message = {"id": n, "method": method, "params": params or {}}
        if session:
            message["sessionId"] = session
        self.out.write(json.dumps(message).encode() + b"\0")
        end = time.time() + timeout
        with self.lock:
            while n not in self.answers:
                if time.time() > end:
                    raise TimeoutError(method)
                self.lock.wait(end - time.time())
            answer = self.answers.pop(n)
        if "error" in answer:
            raise RuntimeError("%s: %s" % (method, answer["error"].get("message")))
        return answer.get("result", {})

    def close(self):
        try:
            self.call("Browser.close", timeout=10)
        except (OSError, RuntimeError, TimeoutError):
            pass
        try:
            self.proc.wait(15)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def find_browser(wanted):
    if wanted:
        return wanted
    if MAC:
        for app in ("Google Chrome", "Chromium", "Microsoft Edge"):
            path = "/Applications/%s.app/Contents/MacOS/%s" % (app, app)
            if os.path.exists(path):
                return path
        return None
    sys.path.insert(0, os.path.join(ROOT, "hub"))
    import linux
    return linux.browser("auto")


# ---- where the desktop itself has the windows ----------------------------------------------------------------------
def mac_desktop(pid):
    """The browser's windows as macOS's window server has them: [(x, y, width, height)] (top-left origin)."""
    script = ("ObjC.import('CoreGraphics'); var all = ObjC.deepUnwrap(ObjC.castRefToObject($.CGWindowListCopyWindowInfo(1, 0)));"
              " JSON.stringify(all.filter(function (w) { return w.kCGWindowOwnerPID === %d && w.kCGWindowLayer === 0; })"
              ".map(function (w) { var b = w.kCGWindowBounds; return [b.X, b.Y, b.Width, b.Height]; }))" % pid)
    done = subprocess.run(["osascript", "-l", "JavaScript", "-e", script], capture_output=True, text=True, timeout=20)
    return [tuple(int(n) for n in w) for w in json.loads(done.stdout)] if done.returncode == 0 else None


def x11_desktop():
    """The top-level windows as the X server has them: [(x, y, width, height)] on the screen (through XWayland too)."""
    import ctypes
    sys.path.insert(0, os.path.join(ROOT, "hub"))
    import linux
    out = []
    with linux._display() as (lib, display):
        if display is None:
            return None
        lib.XGetGeometry.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)] + [ctypes.POINTER(ctypes.c_int)] * 2 \
            + [ctypes.POINTER(ctypes.c_uint)] * 4
        lib.XTranslateCoordinates.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                                              ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong)]
        root = lib.XDefaultRootWindow(display)
        for window in linux._top_windows(lib, display):
            if not linux._is_browser(lib, display, window):
                continue
            r, x, y, w, h, border, depth = (ctypes.c_ulong(), ctypes.c_int(), ctypes.c_int(), ctypes.c_uint(), ctypes.c_uint(),
                                            ctypes.c_uint(), ctypes.c_uint())
            lib.XGetGeometry(display, window, ctypes.byref(r), ctypes.byref(x), ctypes.byref(y), ctypes.byref(w), ctypes.byref(h),
                             ctypes.byref(border), ctypes.byref(depth))
            ax, ay, child = ctypes.c_int(), ctypes.c_int(), ctypes.c_ulong()
            lib.XTranslateCoordinates(display, window, root, 0, 0, ctypes.byref(ax), ctypes.byref(ay), ctypes.byref(child))
            out.append((ax.value, ay.value, w.value, h.value))
    return out


def kwin_desktop(folder):
    """The windows as KWin has them (client area: no title bar or frame): [(x, y, width, height)], through a KWin script
    loaded over this test's own D-Bus session; its print() lines land in KWin's log."""
    tool = shutil.which("qdbus6") or shutil.which("qdbus")
    log_path = os.path.join(folder, "kwin.log")
    if not tool or not os.path.exists(log_path):
        return None
    script = os.path.join(folder, "where.js")
    with open(script, "w") as f:
        f.write("for (const w of workspace.windowList()) { const g = w.clientGeometry; if (w.normalWindow) print('CROSSCHAT-E2E ' + "
                "JSON.stringify([Math.round(g.x), Math.round(g.y), Math.round(g.width), Math.round(g.height)])); }\n")
    mark = os.path.getsize(log_path)
    name = "crosschat-e2e-%d" % time.time_ns()
    number = subprocess.run([tool, "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.loadScript", script, name],
                            capture_output=True, text=True).stdout.strip()
    subprocess.run([tool, "org.kde.KWin", "/Scripting/Script" + number, "org.kde.kwin.Script.run"], capture_output=True)
    time.sleep(1)
    subprocess.run([tool, "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", name], capture_output=True)
    with open(log_path, encoding="utf-8", errors="replace") as f:
        f.seek(mark)
        lines = [line.split("CROSSCHAT-E2E ", 1)[1] for line in f if "CROSSCHAT-E2E " in line]
    return [tuple(json.loads(line)) for line in lines]


# ---- a stand-in for OBS (obs-websocket 5, no password) -------------------------------------------------------------
class OBS:
    """Says the stream started or stopped when told to; answers the two questions the hub asks."""

    def __init__(self):
        self.ws, self.ready = None, asyncio.Event()

    async def handler(self, ws):
        await ws.send(json.dumps({"op": 0, "d": {"obsStudioVersion": "33.0.1", "obsWebSocketVersion": "5.7.6", "rpcVersion": 1}}))
        await ws.recv()
        await ws.send(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}))
        self.ws = ws
        self.ready.set()
        data = {"GetStreamStatus": {"outputActive": False},           # (a stream to the internet, not to this computer)
                "GetStreamServiceSettings": {"streamServiceSettings": {"server": "rtmp://live.example.invalid/app"}}}
        try:
            async for raw in ws:
                d = json.loads(raw)["d"]
                if d.get("requestType") in data:
                    await ws.send(json.dumps({"op": 7, "d": {"requestType": d["requestType"], "requestId": d["requestId"],
                                                             "requestStatus": {"result": True, "code": 100},
                                                             "responseData": data[d["requestType"]]}}))
        except ConnectionClosed:              # (the hub stops at the end of the check)
            pass

    async def stream(self, on):
        state = "OBS_WEBSOCKET_OUTPUT_STARTED" if on else "OBS_WEBSOCKET_OUTPUT_STOPPED"
        await self.ws.send(json.dumps({"op": 5, "d": {"eventType": "StreamStateChanged", "eventIntent": 64,
                                                      "eventData": {"outputActive": on, "outputState": state}}}))


# ---- the check -----------------------------------------------------------------------------------------------------
def stand_in_browser(folder, browser, flags):
    """What the hub's "browser" setting names: a program (an .app on a Mac) that hands its --app window to the running
    throwaway browser (the same profile folder), never to your own."""
    line = "#!/bin/sh\nexec %s %s \"$@\"\n" % (shlex.quote(browser), " ".join(shlex.quote(f) for f in flags))
    if MAC:
        app = os.path.join(folder, "CrossChat test browser.app")
        os.makedirs(os.path.join(app, "Contents", "MacOS"))
        with open(os.path.join(app, "Contents", "Info.plist"), "wb") as f:
            plistlib.dump({"CFBundleExecutable": "browser", "CFBundleIdentifier": "org.crosschat.window-e2e.browser",
                           "CFBundleName": "CrossChat test browser", "CFBundlePackageType": "APPL", "LSUIElement": True}, f)
        path = os.path.join(app, "Contents", "MacOS", "browser")
    else:
        app = path = os.path.join(folder, "browser")
    with open(path, "w") as f:
        f.write(line)
    os.chmod(path, 0o755)
    return app, path


class InProcess:
    """This checkout's hub, run in this program with a stand-in for OBS; the hub's system's way of handling windows
    (AppleScript, X11, user32) is a recorder here, so whatever is placed, moved or closed is the extension's doing."""
    page, page_url, page_box, label = "tiktok", TIKTOK, TIKTOK_BOX, "the TikTok LIVE page"

    async def start(self, folder, app):
        self.obs, self.system = OBS(), []
        self.server = await serve(self.obs.handler, "127.0.0.1", 0)
        home = os.path.join(folder, "crosschat")
        os.makedirs(home)
        config = {"tiktok": "crosschat_e2e", "browser": app, "close_window_seconds_after_stream": 2, "window": rect(CHAT_BOX),
                  "tiktok_window": rect(TIKTOK_BOX), "emotes": {"bttv": False, "ffz": False, "7tv": False}, "logs": {"enabled": False},
                  "remote": {"enabled": False}, "updates": {"check": False},
                  "obs": {"host": "127.0.0.1", "port": self.server.sockets[0].getsockname()[1], "password": ""}}
        with open(os.path.join(home, "config.json"), "w") as f:
            json.dump(config, f)
        sys.path.insert(0, os.path.join(ROOT, "hub"))
        import hub
        self.hub = hub
        hub.configure(["--config", os.path.join(home, "config.json"), "--quiet"])
        hub.start_log()
        hub.place = lambda handle, *where: self.system.append(("place", handle, where))
        hub.close_handle = lambda handle: self.system.append(("close", handle)) if handle else None
        hub.close_window = lambda: self.system.append(("close the chat window",))
        hub.browser_windows = lambda prefix=None: []
        if MAC:
            hub.macos.windows = lambda app, prefix=None: None      # (no AppleScript: as when OBS starts the hub)
        if LINUX:
            hub.linux.windows = lambda app, prefix=None: None      # (no X11: as on Wayland)
        self.task = asyncio.create_task(hub.main())

    def running(self):
        return not self.task.done()

    async def connected(self):
        return bool(self.obs.ws) and self.hub.state["executor"] is not None

    async def open_windows(self):
        await self.obs.stream(True)            # the stream starts: the chat window and the TikTok page open

    def recorded(self):
        return (self.hub.pages.get(self.page) or {}).get("id")

    async def move(self):
        self.hub.CFG["window"] = rect(MOVED_BOX)
        await asyncio.to_thread(get, "/show")
        return MOVED_BOX

    async def close_windows(self):
        await self.obs.stream(False)           # after close_window_seconds_after_stream (2 here), both close

    async def after(self):
        check(self.system == [], "the system's own way (AppleScript, X11, user32) was never needed", "it was asked for %s" % self.system)

    async def stop(self):
        if getattr(self, "task", None):
            self.task.cancel()
            await asyncio.wait({self.task}, timeout=10)
        if getattr(self, "server", None):
            self.server.close()


class StartedByOBS:
    """macOS: OBS itself (OBS.app with a stand-in home folder and only its own plugins, set up as scripts/obs_e2e.py
    does) starts this checkout's hub with the CrossChat script, as for a streamer. macOS refuses AppleScript to
    programs OBS starts, so here too whatever is placed, moved or closed is the extension's doing."""
    page, page_url, page_box, label = "x", "https://studio.x.com/live", X_BOX, "X Live Studio's page (Go live on X, dry run)"

    def __init__(self, obs_app):
        self.obs_app, self.obs = obs_app, None

    async def start(self, folder, app):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import obs_e2e
        found = obs_e2e.mac_obs(self.obs_app)
        if not found:
            raise RuntimeError("no OBS.app at %s" % self.obs_app)
        if not os.path.exists(os.path.join(ROOT, ".venv", "bin", "python3")):
            raise RuntimeError("the OBS script runs the hub with %s/.venv: make it first (python3 -m venv .venv, then "
                               "pip install -r hub/requirements.txt)" % ROOT)
        exe, version = found
        home = os.path.join(folder, "crosschat")
        os.makedirs(home)
        self.config = os.path.join(home, "config.json")
        with open(self.config, "w") as f:
            json.dump({"browser": app, "window": rect(CHAT_BOX), "open_window_on_stream_start": False, "close_window_seconds_after_stream": 2,
                       "x": {"enabled": True, "auto_go_live": False, "window": rect(X_BOX)}, "emotes": {"bttv": False, "ffz": False, "7tv": False},
                       "logs": {"enabled": False}, "remote": {"enabled": False}, "updates": {"check": False}}, f)
        self.log = os.path.join(home, "crosschat.log")
        settings, flags, env = obs_e2e.mac_settings(os.path.join(folder, "obs-home"))
        obs_e2e.obs_settings(settings, version, None, os.path.join(ROOT, "obs", "crosschat.lua"))
        obs_e2e.mac_first_start(settings)
        env = {**os.environ, "CROSSCHAT_CONFIG": self.config, **env}
        self.obs = subprocess.Popen([exe, *flags, *obs_e2e.FLAGS], cwd=os.path.dirname(exe), env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # collected the moment it ends: unreaped, an OBS that has quit still "runs" for the hub (which follows OBS's
        # process id), as it never does for a streamer, whose OBS nobody but the system starts
        threading.Thread(target=self.obs.wait, daemon=True).start()
        info("OBS %s started (a stand-in home folder, its own plugins only); its CrossChat script starts the hub" % version)

    def running(self):
        return self.obs is not None and self.obs.poll() is None

    async def connected(self):
        await asyncio.sleep(3)                 # (the chat tab connects as the hub's window with the extension)
        return True

    async def open_windows(self):
        await asyncio.to_thread(get, "/show")            # Open chat
        await asyncio.to_thread(get, "/x/go?mode=dry")   # Go live on X, as a dry run: X's page opens, nothing is pressed

    def recorded(self):
        return None

    async def move(self):
        """Settings: the window position back to "auto" (the right edge of the main screen), then Open chat."""
        await asyncio.to_thread(post, "/config", {"window": "auto"})
        await asyncio.to_thread(get, "/show")
        sys.path.insert(0, os.path.join(ROOT, "hub"))
        import hub                             # (only to work out where "auto" is, the way the hub does)
        hub.configure(["--config", self.config, "--quiet"])
        return hub.box("auto", "chat")

    async def close_windows(self):
        self.obs.send_signal(signal.SIGTERM)  # OBS quits, as from its menu: the hub closes its windows and leaves

    async def after(self):
        def port_free():
            with socket.socket() as s:
                return s.connect_ex(("127.0.0.1", PORT)) != 0
        left = False
        for _ in range(60):
            if port_free():
                left = True
                break
            await asyncio.sleep(0.5)
        check(left, "the hub left once OBS had closed (with the chat in your tab still open)", "port %d still answers 30 s later" % PORT)
        with open(self.log, encoding="utf-8", errors="replace") as f:
            log = f.read()
        done = [line.split(" INFO ", 1)[1] for line in log.splitlines() if "done by the extension" in line]
        check(all(("window %s: done by the extension" % job) in log for job in ("place chat", "place x", "close x", "close chat")),
              "the hub's log: the extension placed, moved and closed them", "it says %s" % done)

    async def stop(self):
        if self.running():
            self.obs.send_signal(signal.SIGTERM)
            try:
                await asyncio.to_thread(self.obs.wait, 30)
            except subprocess.TimeoutExpired:
                self.obs.kill()


def get(path):
    return urllib.request.urlopen("http://127.0.0.1:%d%s" % (PORT, path), timeout=90).read()


def post(path, body):
    ask = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path), data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(ask, timeout=30).read()


async def scenario(args, browser, folder):
    profile = os.path.join(folder, "profile")
    flags = ["--user-data-dir=" + profile, "--no-first-run", "--no-default-browser-check", "--disable-sync",
             "--disable-component-update", "--disable-background-networking", "--disable-default-apps",
             "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"]
    flags.append("--use-mock-keychain" if MAC else "--password-store=basic")
    if LINUX:
        flags.append("--ozone-platform=" + ("wayland" if args.wayland and not args.xwayland else "x11"))
    wayland = LINUX and args.wayland and not args.xwayland
    tools = DevTools([browser, "--remote-debugging-pipe", "--enable-unsafe-extension-debugging", *flags, "about:blank"],
                     os.path.join(folder, "browser.log"))
    call = lambda method, params=None: asyncio.to_thread(tools.call, method, params)      # (the hub may run in this loop)
    app, program = stand_in_browser(folder, browser, flags)
    hub = StartedByOBS(args.obs) if args.obs else InProcess()
    try:
        version = (await call("Browser.getVersion"))["product"]
        extension = (await call("Extensions.loadUnpacked", {"path": EXTENSION}))["id"]
        check(bool(extension), "%s with a throwaway profile, this checkout's extension loaded over DevTools" % version)

        async def windows():
            """Every page and the window it is in: [{url, window, bounds}] (DevTools' window ids are the extension's)."""
            out = []
            for target in (await call("Target.getTargets"))["targetInfos"]:
                if target["type"] == "page":
                    try:
                        found = await call("Browser.getWindowForTarget", {"targetId": target["targetId"]})
                    except RuntimeError:
                        continue
                    b = found["bounds"]
                    out.append({"url": target["url"], "window": found["windowId"], "target": target["targetId"],
                                "bounds": (b.get("left"), b.get("top"), b.get("width"), b.get("height"))})
            return out

        async def until(test, seconds, step=0.25):
            end = time.time() + seconds
            while time.time() < end:
                found = await test()
                if found:
                    return found
                await asyncio.sleep(step)
            return None

        def desktop():
            if MAC:
                return mac_desktop(tools.proc.pid)
            if wayland:
                return kwin_desktop(os.environ.get("CROSSCHAT_E2E_KWIN", ""))
            return x11_desktop()

        await hub.start(folder, app)

        async def hub_up():
            try:
                return await asyncio.to_thread(get, "/version")
            except OSError:
                return None
        up = await until(hub_up, 60)
        if not check(bool(up) and hub.running(), "the hub answers on 127.0.0.1:%d" % PORT,
                     "no answer" if hub.running() else "another program took the port, or OBS ended"):
            return                                    # (the hub leaves at once when the port is taken: nothing to check)

        # your windows: they must keep their place and stay open
        async def ordinary(url, where):
            target = (await call("Target.createTarget", {"url": url, "newWindow": True}))["targetId"]
            window = (await call("Browser.getWindowForTarget", {"targetId": target}))["windowId"]
            await call("Browser.setWindowBounds", {"windowId": window, "bounds": rect(where, ("left", "top", "width", "height"))})
            return window
        await ordinary(CHAT, (600, 420, 500, 360))
        await ordinary(hub.page_url, (620, 440, 500, 360))

        async def app_window(url, where):
            """An --app window opened the way the hub opens one (on a Mac through Launch Services, `open -n -a`, which
            took over 30 s the first time for the stand-in browser app on a fresh GitHub Mac: done here first)."""
            before = {w["window"] for w in await windows()}
            args = ["--app=" + url, "--window-position=%d,%d" % where[:2], "--window-size=%d,%d" % where[2:]]
            subprocess.Popen(["open", "-n", "-a", app, "--args", *args] if MAC else [program, *args],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return await until(lambda: _new(before, url), 120 if MAC else 30)

        async def _new(before, url):
            return next((w for w in await windows() if w["window"] not in before and w["url"].split("#")[0].startswith(url)), None)
        other = await app_window(hub.page_url + "/someone_else" if args.obs else "https://www.tiktok.com/@someone_else/live", (640, 460, 400, 300))
        studio = await app_window(CHAT + "studio", (660, 480, 400, 300))
        check(bool(other and studio), "--app windows open in the running browser, as the hub opens them")
        if studio:
            info("asked for (660, 480, 400, 300) on the command line, a running browser opened the --app window at %s: "
                 "--window-position and --window-size count only when the browser starts with that window" % (studio["bounds"],))
        mine = {w["window"]: w["bounds"] for w in await windows()}
        info("your windows: %d (the first browser window, the chat in a tab, %s in a tab, another page of that site and the "
             "Theme Studio as --app windows)" % (len(mine), hub.label))
        check(bool(await until(hub.connected, 15)), "the chat in a tab of an ordinary window connected as the window with the extension")

        await hub.open_windows()

        async def crosschat(url):
            return next((w for w in await windows() if w["window"] not in mine and w["url"].split("#")[0] == url), None)

        def at(where):
            return "made it %dx%d (on Wayland, KWin places it)" % tuple(where[2:]) if wayland else "put it at %s" % (tuple(where),)

        async def placed(url, where):
            """The window at `url`, once the browser has it at `where` (on Wayland: of that size; the place is KWin's)."""
            w = await crosschat(url)
            return w if w and (w["bounds"][2:] == tuple(where[2:]) if wayland else w["bounds"] == tuple(where)) else None
        chat = await until(lambda: placed(CHAT, CHAT_BOX), 45)
        check(bool(chat), "the chat window opened and the extension %s" % at(CHAT_BOX),
              "now %s" % (((await crosschat(CHAT)) or {}).get("bounds"),))
        page = await until(lambda: placed(hub.page_url, hub.page_box), 45)
        check(bool(page), "%s opened and the extension %s" % (hub.label, at(hub.page_box)),
              "now %s" % (((await crosschat(hub.page_url)) or {}).get("bounds"),))
        if not args.obs:
            recorded = await until(lambda: asyncio.sleep(0, hub.recorded()), 15)   # (once the launch returned too)
            check(bool(page) and recorded == page["window"], "the hub recorded the page's window (%s)" % recorded)

        async def on_desktop(where, label):
            seen = await asyncio.to_thread(desktop)
            if seen is None:
                info("%s: this desktop can't be asked where its windows are" % label)
            elif wayland:
                same_size = any(tuple(s[2:]) == tuple(where[2:]) for s in seen)
                check(same_size, "%s: KWin has a window of exactly %dx%d" % ((label,) + tuple(where[2:])), "KWin has %s" % seen)
                info("%s: on Wayland the desktop places windows (asked for %s); KWin has the windows at %s"
                     % (label, tuple(where[:2]), [s[:2] for s in seen]))
            else:
                check(tuple(where) in [tuple(s) for s in seen], "%s: the desktop itself has a window exactly at %s" % (label, tuple(where)),
                      "it has %s" % seen)
        if chat:
            await on_desktop(CHAT_BOX, "the chat window")
        if page:
            await on_desktop(hub.page_box, "the page")

        moved_box = tuple(await hub.move())    # Open chat, with another place for the chat window
        moved = await until(lambda: placed(CHAT, moved_box), 15)
        check(bool(moved), "Open chat: the extension %s" % at(moved_box), "now %s" % (((await crosschat(CHAT)) or {}).get("bounds"),))
        if moved:
            await on_desktop(moved_box, "the moved chat window")

        started = time.time()
        await hub.close_windows()

        async def closed():
            return not [w for w in await windows() if w["window"] not in mine]
        gone = await until(closed, 30)
        check(bool(gone), "the chat window and the page closed (%.1f s later)" % (time.time() - started),
              "still open: %s" % [w["url"] for w in await windows() if w["window"] not in mine])
        await asyncio.sleep(1)
        now = {w["window"]: w["bounds"] for w in await windows()}
        if wayland:                            # (the place a Wayland browser reports for its windows means nothing)
            mine, now = {k: v[2:] for k, v in mine.items()}, {k: v[2:] for k, v in now.items()}
        check(now == mine, "your windows were left alone: all %d still open, each %s" % (len(mine), "its size" if wayland else "where it was"),
              "before %s, now %s" % (mine, now))
        await hub.after()
        if wayland:
            info("Wayland: the browser reports the place it asked for; where KWin really puts a window is KWin's choice")
    finally:
        await asyncio.to_thread(tools.close)            # first: the chat pages' connections to the hub end with it
        await hub.stop()
        if MAC:
            subprocess.run([LSREGISTER, "-u", app], capture_output=True)


def check_here(args):
    """The check itself, on this desktop (on Linux: inside the folder and display of its own set up below)."""
    browser = find_browser(args.browser)
    if not browser:
        print("No Chrome, Chromium or Edge found: name one with --browser.")
        return 2
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            print("Port %d is taken (a CrossChat hub running?): close it first." % PORT)
            return 2
    folder = os.environ.get("CROSSCHAT_E2E_HOME") or tempfile.mkdtemp(prefix="crosschat-window-e2e-")
    folder = os.path.join(folder, "check")
    os.makedirs(folder, exist_ok=True)
    faulthandler.dump_traceback_later(900, exit=True)  # a check that hangs says where, and ends
    try:
        asyncio.run(scenario(args, browser, folder))
    except Exception as error:  # noqa: BLE001 (any surprise is a failed check, with its reason)
        traceback.print_exc()
        check(False, "the check ran to the end", "%s: %s" % (type(error).__name__, error))
    faulthandler.cancel_dump_traceback_later()
    if failures:
        log = os.path.join(folder, "crosschat", "crosschat.log")
        if os.path.exists(log):
            print("---- crosschat.log (the end) ----")
            with open(log, encoding="utf-8", errors="replace") as f:
                print("".join(f.readlines()[-40:]))
    if args.keep:
        print("kept: %s" % folder)
    elif not os.environ.get("CROSSCHAT_E2E_HOME"):
        shutil.rmtree(os.path.dirname(folder), ignore_errors=True)
    print("%d failed" % len(failures) if failures else "all passed")
    return 1 if failures else 0


# ---- Linux: a folder, a D-Bus session and a display of its own ------------------------------------------------------
def linux_outside(args):
    """Run this script again inside a throwaway home, runtime folder and D-Bus session, so the browser and KWin never
    reach your desktop session, keyring or settings."""
    box = tempfile.mkdtemp(prefix="crosschat-window-e2e-")
    keep = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "XAUTHORITY",
                                                              "XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP", "SESSION_MANAGER")}
    home = os.path.join(box, "home")
    run = os.path.join(box, "run")
    os.makedirs(home)
    os.makedirs(run, mode=0o700)
    keep.update(HOME=home, XDG_RUNTIME_DIR=run, XDG_CONFIG_HOME=os.path.join(home, ".config"), XDG_DATA_HOME=os.path.join(home, ".local", "share"),
                XDG_CACHE_HOME=os.path.join(home, ".cache"), XDG_STATE_HOME=os.path.join(home, ".local", "state"),
                CROSSCHAT_E2E_HOME=box, PYTHONNOUSERSITE="1")
    try:
        code = subprocess.call(["dbus-run-session", "--", sys.executable, os.path.abspath(__file__), "--inside", *sys.argv[1:]], env=keep)
    finally:
        for mount in (os.path.join(run, "doc"), os.path.join(run, "gvfs")):      # (portals a browser wakes up)
            for tool in ("fusermount3", "fusermount"):
                if os.path.ismount(mount) and shutil.which(tool):
                    subprocess.run([tool, "-u", mount], capture_output=True)
        if args.keep:
            print("kept: %s" % box)
        else:
            shutil.rmtree(box, ignore_errors=True)
    return code


def linux_inside(args):
    box = os.environ["CROSSCHAT_E2E_HOME"]
    if args.wayland:                          # KWin on a virtual screen; this script again as its session
        session = os.path.join(box, "session.sh")
        with open(session, "w") as f:
            f.write("#!/bin/sh\nexec %s %s --session %s > %s 2>&1\n" % (
                shlex.quote(sys.executable), shlex.quote(os.path.abspath(__file__)),
                " ".join(shlex.quote(a) for a in sys.argv[1:] if a != "--inside"), shlex.quote(os.path.join(box, "session.log"))))
        os.chmod(session, 0o755)
        env = dict(os.environ, QT_LOGGING_RULES="kwin_scripting.debug=true", CROSSCHAT_E2E_KWIN=box)
        command = ["kwin_wayland", "--virtual", "--socket", "crosschat-e2e", "--width", "1920", "--height", "1080", "--no-lockscreen",
                   "--no-global-shortcuts", "--no-kactivities", "--exit-with-session", session]
        if args.xwayland:
            command.insert(1, "--xwayland")
        with open(os.path.join(box, "kwin.log"), "wb") as log:
            kwin = subprocess.Popen(command, env=env, stdout=log, stderr=log)
            try:
                kwin.wait(600)
            except subprocess.TimeoutExpired:
                kwin.kill()
        result = os.path.join(box, "result")
        if os.path.exists(os.path.join(box, "session.log")):              # what the check said, inside KWin
            with open(os.path.join(box, "session.log"), errors="replace") as f:
                print(f.read(), end="", flush=True)
        if not os.path.exists(result):
            print("KWin's session didn't finish: see kwin.log (--keep keeps it)")
            with open(os.path.join(box, "kwin.log"), errors="replace") as f:
                print("".join(f.readlines()[-30:]))
            return 1
        with open(result) as f:
            return int(f.read() or 1)
    display = next(n for n in range(90, 200) if not os.path.exists("/tmp/.X11-unix/X%d" % n) and not os.path.exists("/tmp/.X%d-lock" % n))
    xvfb = subprocess.Popen(["Xvfb", ":%d" % display, "-screen", "0", "1920x1080x24", "-nolisten", "tcp"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            if os.path.exists("/tmp/.X11-unix/X%d" % display):
                break
            time.sleep(0.25)
        os.environ["DISPLAY"] = ":%d" % display
        info("an Xvfb display of its own (:%d, 1920x1080), no window manager" % display)
        return check_here(args)
    finally:
        xvfb.terminate()
        xvfb.wait(10)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--browser", help="the browser program (Chrome, Chromium, Edge or Brave)")
    parser.add_argument("--wayland", action="store_true", help="Linux: on KWin's virtual screen, the browser as a Wayland program")
    parser.add_argument("--xwayland", action="store_true", help="with --wayland: the browser through KWin's XWayland instead")
    parser.add_argument("--obs", nargs="?", const="/Applications/OBS.app",
                        help="macOS: OBS.app starts the hub, with the CrossChat script (default /Applications/OBS.app)")
    parser.add_argument("--keep", action="store_true", help="keep the test folder")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--session", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not (MAC or LINUX):
        print("This check runs on macOS and Linux (see the top of this file).")
        return 2
    if args.obs and not MAC:
        print("--obs is for macOS: OBS for Mac refuses AppleScript to the programs it starts, the case it checks.")
        return 2
    if LINUX and args.session:               # inside KWin
        info("KWin on a virtual screen (1920x1080), the browser %s" % ("through XWayland" if args.xwayland else "as a Wayland program"))
        code = check_here(args)
        with open(os.path.join(os.environ["CROSSCHAT_E2E_HOME"], "result"), "w") as f:
            f.write(str(code))
        return code
    if LINUX and args.inside:
        return linux_inside(args)
    if LINUX:
        return linux_outside(args)
    return check_here(args)


if __name__ == "__main__":
    sys.exit(main())
