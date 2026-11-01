"""macOS (beta): the few jobs the hub does with Windows' own tools, done the Mac way.

  windows / place / close   the browser's own AppleScript dictionary (Chrome, Edge and Chromium all have one). macOS
                            asks once whether CrossChat may control the browser; if that's refused, windows still open
                            where they should, CrossChat just can't move or close them afterwards
  work_area                 the main screen without the menu bar and the Dock (AppKit, through osascript)
  message_box               a plain alert (osascript)
  running                   whether a process (OBS) is still there

Nothing here sends anything anywhere: it all stays on this Mac.
"""
import asyncio
import json
import os
import subprocess
import threading
import time

OBS_SETTINGS = os.path.expanduser("~/Library/Application Support/obs-studio")
BROWSERS = {"chrome": "Google Chrome.app", "edge": "Microsoft Edge.app", "chromium": "Chromium.app"}
QUIET = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}

# One small script for every window job: the browser is named by its .app path, so the right one answers even
# when several are installed, and a browser that isn't running is never started just to be asked.
WINDOWS = """
function run(argv) {
  var app = Application(argv[0]);
  if (!app.running()) return '[]';
  if (argv[1] === 'list') {
    var ids = app.windows.id(), names = app.windows.name(), out = [];
    for (var i = 0; i < ids.length; i++) if (String(names[i]).indexOf(argv[2]) === 0) out.push(ids[i]);
    return JSON.stringify(out);
  }
  if (argv[1] === 'close-titled') {
    var all = app.windows.id(), titles = app.windows.name();
    for (var j = 0; j < all.length; j++) if (String(titles[j]).indexOf(argv[2]) === 0) app.windows.byId(all[j]).close();
    return 'ok';
  }
  var w = app.windows.byId(Number(argv[2]));
  if (!w.exists()) return 'gone';
  if (argv[1] === 'close') w.close();
  if (argv[1] === 'place') w.bounds = {x: Number(argv[3]), y: Number(argv[4]), width: Number(argv[5]), height: Number(argv[6])};
  return 'ok';
}
"""
SCREEN = """
ObjC.import('AppKit');
var s = $.NSScreen.screens.objectAtIndex(0), f = s.frame, v = s.visibleFrame;
JSON.stringify([v.origin.x, f.size.height - v.origin.y - v.size.height, v.origin.x + v.size.width, f.size.height - v.origin.y]);
"""
_screen = {"at": 0.0, "area": (0, 25, 1440, 900)}   # a common MacBook screen until macOS answers
_refused = {"until": 0.0}                    # after macOS says no (or its question goes unanswered), leave it alone a while
BACK_OFF = 60


def _script(source, *argv, timeout=10):
    """Run a JavaScript for Automation script; its answer, or None when macOS or the browser refused."""
    try:
        done = subprocess.run(["osascript", "-l", "JavaScript", "-e", source, *[str(a) for a in argv]], capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _browser(app, *argv):
    """A window job for the browser at `app`. Apple Events to a browser take a moment at most; one that hangs means
    macOS is still asking the person (or was told no), so CrossChat stops asking for a minute instead of waiting."""
    if time.time() < _refused["until"]:
        return None
    found = _script(WINDOWS, app, *argv, timeout=3)
    if found is None:
        _refused["until"] = time.time() + BACK_OFF
    return found


def _later(job, *argv):
    """Moving and closing windows needs no answer: done on the side, so the hub never waits for it."""
    threading.Thread(target=job, args=argv, daemon=True).start()


def bundle(path):
    """The .app folder a browser path points into ('.../Google Chrome.app/Contents/MacOS/Google Chrome' -> '.../Google Chrome.app')."""
    path = os.path.expanduser(str(path))
    if "/Contents/MacOS/" in path:
        path = path.split("/Contents/MacOS/")[0]
    return path.rstrip("/")


def browser(want):
    """The browser the windows open in: "auto" (Chrome, else Edge, else Chromium), "chrome", "edge", "chromium" or a path
    (the .app or the program inside it). Its .app folder, or None."""
    if want not in ("auto", *BROWSERS):
        found = bundle(want)
        return found if found.endswith(".app") and os.path.isdir(found) else None
    for name in (["chrome", "edge", "chromium"] if want == "auto" else [want]):
        for folder in ("/Applications", os.path.expanduser("~/Applications")):
            path = os.path.join(folder, BROWSERS[name])
            if os.path.isdir(path):
                return path
    return None


def windows(app, prefix=None):
    """The browser's windows whose title starts with `prefix`, as handles (app, window id); None when macOS refused."""
    if not app:
        return []
    found = _browser(app, "list", prefix or "")
    if found is None:
        return None
    try:
        return [(app, int(i)) for i in json.loads(found)]
    except (ValueError, TypeError):
        return []


def place(handle, x, y, width, height):
    if handle:
        _later(_browser, handle[0], "place", handle[1], x, y, width, height)


def close(handle):
    if handle:
        _later(_browser, handle[0], "close", handle[1])


def close_titled(app, prefix):
    """Close the browser's windows whose title starts with `prefix` (the chat window)."""
    if app:
        _later(_browser, app, "close-titled", prefix)


def work_area():
    """The main screen without the menu bar and the Dock: (left, top, right, bottom), top-left origin like the browsers'."""
    if time.time() - _screen["at"] > 300:
        found = _script(SCREEN, timeout=5)
        try:
            area = tuple(int(round(n)) for n in json.loads(found))
            if len(area) == 4 and area[2] > area[0] and area[3] > area[1]:
                _screen["area"] = area
        except (TypeError, ValueError):
            pass
        _screen["at"] = time.time()
    return _screen["area"]


async def open_app(app, url, where):
    """A bare window of the browser on `url` at `where` (x, y, width, height); its handle when CrossChat may manage it."""
    before = await asyncio.to_thread(windows, app)
    command = ["open", "-n", "-a", app, "--args", "--app=" + url, "--window-position=%d,%d" % where[:2], "--window-size=%d,%d" % where[2:]]
    try:
        await asyncio.to_thread(subprocess.run, command, timeout=30, **QUIET)
    except (OSError, subprocess.SubprocessError):
        return None
    if before is None:                      # no say over the browser's windows: it opened where it was asked, that's all
        return None
    for _ in range(40):
        await asyncio.sleep(0.25)
        now = await asyncio.to_thread(windows, app)
        if now is None:                      # macOS is asking the person, or was told no: the window is open all the same
            return None
        new = [h for h in now if h not in before]
        if new:
            place(new[0], *where)
            return new[0]
    return None


def message_box(text):
    """A plain alert for the person at the Mac (blocks until it's closed: call it from a thread)."""
    try:
        subprocess.run(["osascript", "-e", "on run argv", "-e", 'display alert "CrossChat" message (item 1 of argv) as warning',
                        "-e", "end run", str(text)], timeout=3600, **QUIET)
    except (OSError, subprocess.SubprocessError):
        pass


def running(pid):
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
