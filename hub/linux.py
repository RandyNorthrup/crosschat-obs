"""Linux: the few jobs the hub does with Windows' own tools, done the Linux way.

  windows / place / close   X11 (libX11, through ctypes), for when the CrossChat extension isn't there to do it (it does
                            it with the browser's own window API, see extension/windows.js): the browser's windows are
                            found by their class and title, moved with an ordinary configure request and closed with
                            WM_DELETE_WINDOW, as a window manager does. On Wayland this reaches the browser only when it
                            runs through XWayland
  work_area                 the desktop's work area (_NET_WORKAREA: the screen without its panels), else the screen
  message_box               zenity or kdialog, whichever the desktop has
  running                   whether a process (OBS) is still there

Nothing here sends anything anywhere: it all stays on this computer.
"""
import asyncio
import contextlib
import ctypes
import ctypes.util
import os
import shutil
import subprocess
import threading
import time


def _config_home():
    """$XDG_CONFIG_HOME, else ~/.config (where OBS keeps its settings, as every desktop program does)."""
    folder = os.environ.get("XDG_CONFIG_HOME") or ""
    return folder if os.path.isabs(folder) else os.path.expanduser("~/.config")


FLATPAK_OBS = os.path.expanduser("~/.var/app/com.obsproject.Studio/config/obs-studio")     # OBS from Flathub


def _obs_settings():
    """OBS's settings folder: the usual one, or OBS from Flathub's when only that one is there. (The OBS script passes
    the folder of the OBS that started the hub with --obs-config; this is for a hub started otherwise.)"""
    usual = os.path.join(_config_home(), "obs-studio")
    return FLATPAK_OBS if not os.path.isdir(usual) and os.path.isdir(FLATPAK_OBS) else usual


OBS_SETTINGS = _obs_settings()
# the programs each browser installs as, newest naming first (a snap's are in /snap/bin)
BROWSERS = {"chrome": ("google-chrome-stable", "google-chrome"), "edge": ("microsoft-edge-stable", "microsoft-edge"),
            "chromium": ("chromium", "chromium-browser"), "brave": ("brave-browser", "brave")}
# their windows' WM_CLASS class (Google-chrome, Microsoft-edge, Chromium or Chromium-browser, Brave-browser), lowercase
CLASSES = (b"google-chrome", b"microsoft-edge", b"chromium", b"brave-browser")
EXTRA_PATH = "/snap/bin"
QUIET = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
SCREEN = (0, 0, 1920, 1080)                  # when there's no X display to ask
CLIENT_MESSAGE = 33                          # X's ClientMessage event


def browser(want):
    """The browser the windows open in: "auto" (Chrome, else Edge, else Chromium, else Brave), one of those names, or a
    program: a full path, or a command on PATH. Its full path, or None."""
    want = str(want or "auto")
    where = os.environ.get("PATH", "") + os.pathsep + EXTRA_PATH
    if want in ("auto", *BROWSERS):
        for name in (list(BROWSERS) if want == "auto" else [want]):
            for command in BROWSERS[name]:
                found = shutil.which(command, path=where)
                if found:
                    return found
        return None
    path = os.path.expanduser(want)
    if os.path.isabs(path):
        return path if os.path.isfile(path) and os.access(path, os.X_OK) else None
    return shutil.which(path, path=where)


# ---- X11 ----------------------------------------------------------------------------------------------------------
class _ClientMessage(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int), ("display", ctypes.c_void_p),
                ("window", ctypes.c_ulong), ("message_type", ctypes.c_ulong), ("format", ctypes.c_int), ("l", ctypes.c_long * 5)]


class _Event(ctypes.Union):
    _fields_ = [("xclient", _ClientMessage), ("pad", ctypes.c_long * 24)]


class _Attributes(ctypes.Structure):          # XWindowAttributes
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int), ("width", ctypes.c_int), ("height", ctypes.c_int), ("border_width", ctypes.c_int),
                ("depth", ctypes.c_int), ("visual", ctypes.c_void_p), ("root", ctypes.c_ulong), ("klass", ctypes.c_int),
                ("bit_gravity", ctypes.c_int), ("win_gravity", ctypes.c_int), ("backing_store", ctypes.c_int),
                ("backing_planes", ctypes.c_ulong), ("backing_pixel", ctypes.c_ulong), ("save_under", ctypes.c_int),
                ("colormap", ctypes.c_ulong), ("map_installed", ctypes.c_int), ("map_state", ctypes.c_int),
                ("all_event_masks", ctypes.c_long), ("your_event_mask", ctypes.c_long), ("do_not_propagate_mask", ctypes.c_long),
                ("override_redirect", ctypes.c_int), ("screen", ctypes.c_void_p)]


VIEWABLE = 2                                 # map_state IsViewable


_ErrorHandler = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
_ignore_errors = _ErrorHandler(lambda display, error: 0)   # Xlib's own handler ends the program on any error, such as a
_x = {"lib": None, "tried": False}                           # window that closed a moment ago: CrossChat just carries on
_one_job = threading.Lock()                                  # (each job has a connection of its own, one job at a time)


def _xlib():
    """libX11, or None where there is none."""
    if not _x["tried"]:
        _x["tried"] = True
        try:
            lib = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
        except OSError:
            return None
        ref, word, num, unum = ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_uint
        signatures = {
            "XOpenDisplay": (ref, [ctypes.c_char_p]),
            "XCloseDisplay": (num, [ref]),
            "XDefaultRootWindow": (word, [ref]),
            "XDefaultScreen": (num, [ref]),
            "XDisplayWidth": (num, [ref, num]),
            "XDisplayHeight": (num, [ref, num]),
            "XInternAtom": (word, [ref, ctypes.c_char_p, num]),
            "XGetWindowProperty": (num, [ref, word, word, ctypes.c_long, ctypes.c_long, num, word, ctypes.POINTER(word), ctypes.POINTER(num),
                                         ctypes.POINTER(word), ctypes.POINTER(word), ctypes.POINTER(ref)]),
            "XQueryTree": (num, [ref, word, ctypes.POINTER(word), ctypes.POINTER(word), ctypes.POINTER(ref), ctypes.POINTER(unum)]),
            "XGetWindowAttributes": (num, [ref, word, ctypes.POINTER(_Attributes)]),
            "XFree": (num, [ref]),
            "XMoveResizeWindow": (num, [ref, word, num, num, unum, unum]),
            "XSendEvent": (num, [ref, word, num, ctypes.c_long, ctypes.POINTER(_Event)]),
            "XSync": (num, [ref, num]),
            "XSetErrorHandler": (ref, [_ErrorHandler]),
        }
        try:
            for name, (restype, argtypes) in signatures.items():
                function = getattr(lib, name)
                function.restype, function.argtypes = restype, argtypes
        except AttributeError:
            return None
        lib.XSetErrorHandler(_ignore_errors)
        _x["lib"] = lib
    return _x["lib"]


@contextlib.contextmanager
def _display():
    """(libX11, a connection to the X display), or (None, None) when there's no X display (no desktop, or Wayland
    without XWayland)."""
    lib = _xlib() if os.environ.get("DISPLAY") else None
    if lib is None:
        yield None, None
        return
    with _one_job:
        display = lib.XOpenDisplay(None)
        if not display:
            yield None, None
            return
        try:
            yield lib, display
        finally:
            lib.XCloseDisplay(display)


def _property(lib, display, window, name):
    """A window property: a list of numbers (32-bit formats), bytes (8-bit), or None when the window hasn't got it."""
    atom = lib.XInternAtom(display, name.encode(), 1)      # only if it exists: no atom, no such property anywhere
    if not atom:
        return None
    kind, size, count, left, data = ctypes.c_ulong(), ctypes.c_int(), ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_void_p()
    if lib.XGetWindowProperty(display, window, atom, 0, 1 << 16, 0, 0, ctypes.byref(kind), ctypes.byref(size), ctypes.byref(count),
                              ctypes.byref(left), ctypes.byref(data)) != 0 or not data.value:
        return None
    try:
        if size.value == 32:                 # (Xlib hands 32-bit items over as C longs)
            return list((ctypes.c_ulong * count.value).from_address(data.value))
        if size.value == 8:
            return ctypes.string_at(data.value, count.value)
        return None
    finally:
        lib.XFree(data)


def _title(lib, display, window):
    title = _property(lib, display, window, "_NET_WM_NAME")
    if isinstance(title, bytes):
        return title.decode("utf-8", "replace")
    title = _property(lib, display, window, "WM_NAME")
    return title.decode("latin-1") if isinstance(title, bytes) else ""


def _is_browser(lib, display, window):
    """Whether the window is a Chromium browser's (its WM_CLASS class, the second of its two names)."""
    names = _property(lib, display, window, "WM_CLASS")
    if not isinstance(names, bytes):
        return False
    kind = (names.split(b"\0") + [b"", b""])[1].lower()
    return kind.startswith(CLASSES)


def _shown(lib, display, window):
    """Whether a window is on screen as a window of its own (not hidden, not a menu or tooltip)."""
    seen = _Attributes()
    return bool(lib.XGetWindowAttributes(display, window, ctypes.byref(seen))) and seen.map_state == VIEWABLE and not seen.override_redirect


def _top_windows(lib, display):
    """The windows the window manager manages; with none (a bare X server), the top-level windows on screen that have a
    title (a browser keeps hidden ones of its own there too)."""
    root = lib.XDefaultRootWindow(display)
    managed = _property(lib, display, root, "_NET_CLIENT_LIST")
    if isinstance(managed, list):
        return managed
    parent, children, count = ctypes.c_ulong(), ctypes.c_void_p(), ctypes.c_uint()
    if not lib.XQueryTree(display, root, ctypes.byref(ctypes.c_ulong()), ctypes.byref(parent), ctypes.byref(children), ctypes.byref(count)):
        return []
    try:
        found = list((ctypes.c_ulong * count.value).from_address(children.value)) if children.value else []
    finally:
        if children.value:
            lib.XFree(children)
    return [w for w in found if _shown(lib, display, w) and _title(lib, display, w)]


def windows(app, prefix=None):
    """The browser's windows whose title starts with `prefix`, as X window ids; None when there's no X display to ask."""
    if not app:
        return []
    with _display() as (lib, display):
        if display is None:
            return None
        return [int(w) for w in _top_windows(lib, display)
                if _is_browser(lib, display, w) and (prefix is None or _title(lib, display, w).startswith(prefix))]


def _later(job, *argv):
    """Moving and closing windows needs no answer: done on the side, so the hub never waits for it."""
    threading.Thread(target=job, args=argv, daemon=True).start()


def _move(handle, x, y, width, height):
    with _display() as (lib, display):
        if display is not None:
            lib.XMoveResizeWindow(display, handle, x, y, max(1, width), max(1, height))
            lib.XSync(display, 0)


def _close(handle):
    """Ask the window to close, as its close button does (WM_DELETE_WINDOW). Only a browser window: a window id that
    has since gone to another program is left alone."""
    with _display() as (lib, display):
        if display is None or not _is_browser(lib, display, handle):
            return
        event = _Event()
        event.xclient.type, event.xclient.window, event.xclient.format = CLIENT_MESSAGE, handle, 32
        event.xclient.message_type = lib.XInternAtom(display, b"WM_PROTOCOLS", 0)
        event.xclient.l[0] = lib.XInternAtom(display, b"WM_DELETE_WINDOW", 0)
        lib.XSendEvent(display, handle, 0, 0, ctypes.byref(event))
        lib.XSync(display, 0)


def place(handle, x, y, width, height):
    if handle:
        _later(_move, handle, x, y, width, height)


def close(handle):
    if handle:
        _later(_close, handle)


def close_titled(app, prefix):
    """Close the browser's windows whose title starts with `prefix` (the chat window)."""
    def job():
        for handle in windows(app, prefix) or []:
            _close(handle)
    if app:
        _later(job)


def work_area():
    """The desktop without its panels: (left, top, right, bottom). With several screens, X calls them one desktop."""
    with _display() as (lib, display):
        if display is None:
            return SCREEN
        area = _property(lib, display, lib.XDefaultRootWindow(display), "_NET_WORKAREA")
        if isinstance(area, list) and len(area) >= 4 and area[2] > 0 and area[3] > 0:
            return int(area[0]), int(area[1]), int(area[0] + area[2]), int(area[1] + area[3])
        screen = lib.XDefaultScreen(display)
        return 0, 0, lib.XDisplayWidth(display, screen), lib.XDisplayHeight(display, screen)


async def open_app(app, url, where, place_it=True, wait=30):
    """A bare window of the browser on `url` at `where` (x, y, width, height); its handle when CrossChat may manage it.
    A running browser opens it where it likes (it takes --window-position and --window-size only when it starts with
    that window): with `place_it` it is then moved to `where`. A browser starting cold took about 10 seconds to show
    its first window in our tests (GitHub's Ubuntu machines, a new profile), so it is looked for for up to `wait`."""
    before = await asyncio.to_thread(windows, app)
    command = [app, "--app=" + url, "--window-position=%d,%d" % where[:2], "--window-size=%d,%d" % where[2:]]
    try:
        started = subprocess.Popen(command, start_new_session=True, **QUIET)
    except OSError:
        return None
    threading.Thread(target=started.wait, daemon=True).start()     # collected when it hands over to a running browser
    if before is None:                       # no X display to manage windows on: it opened where the desktop put it
        return None
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        await asyncio.sleep(0.25)
        now = await asyncio.to_thread(windows, app)
        if now is None:
            return None
        new = [h for h in now if h not in before]
        if new:
            if place_it:
                place(new[0], *where)
            return new[0]
    return None


def message_box(text):
    """A plain warning for the person at the computer (blocks until it's closed: call it from a thread). Nothing when
    the desktop has neither zenity nor kdialog, or there's no desktop."""
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return
    tools = [["zenity", "--warning", "--no-markup", "--title=CrossChat", "--text=" + str(text)],
             ["kdialog", "--title", "CrossChat", "--sorry", str(text)]]
    if "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", ""):
        tools.reverse()
    for command in tools:
        if shutil.which(command[0]):
            try:
                subprocess.run(command, timeout=3600, **QUIET)
            except (OSError, subprocess.SubprocessError):
                pass
            return


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
