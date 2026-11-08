"""Linux: hub/linux.py, the hub's Linux paths and Tailscale on Linux. The rules run everywhere; what needs Linux says
so. One test opens a real browser window under X the system's way (an Xvfb display, a throwaway browser profile): it
runs only when CROSSCHAT_WINDOW_TESTS=1, so it never touches anyone's own browser. (The extension's way, on X11 and
Wayland: scripts/window_e2e.py.)"""
import asyncio
import os
import shutil
import socket
import stat
import sys
import time

import hub
import linux
import pytest
import tailscale

linux_only = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="needs Linux")


def test_browsers_are_found_by_name_in_order(monkeypatch):
    installed = {"microsoft-edge-stable": "/usr/bin/microsoft-edge-stable", "chromium-browser": "/snap/bin/chromium-browser",
                 "brave-browser": "/usr/bin/brave-browser"}
    monkeypatch.setattr(linux.shutil, "which", lambda name, path=None: installed.get(name))
    assert linux.browser("auto") == "/usr/bin/microsoft-edge-stable"            # Chrome first, but it isn't there
    assert linux.browser("chromium") == "/snap/bin/chromium-browser"
    assert linux.browser("brave") == "/usr/bin/brave-browser"
    assert linux.browser("chrome") is None
    installed["google-chrome"] = "/usr/bin/google-chrome"
    assert linux.browser("auto") == linux.browser("chrome") == "/usr/bin/google-chrome"
    assert linux.browser("vivaldi") is None                                       # a command that isn't there


@linux_only
def test_a_browser_can_be_a_program_of_your_own(tmp_path):
    mine = tmp_path / "my-browser"
    mine.write_text("#!/bin/sh\n")
    assert linux.browser(str(mine)) is None                                       # not runnable
    mine.chmod(mine.stat().st_mode | stat.S_IXUSR)
    assert linux.browser(str(mine)) == str(mine)
    assert linux.browser(str(tmp_path / "missing")) is None


def test_obs_settings_follow_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert linux._config_home() == str(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative/is/ignored")
    assert linux._config_home() == os.path.expanduser("~/.config")


def test_without_an_x_display_windows_open_but_are_left_alone(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    assert linux.windows("/usr/bin/google-chrome", "CrossChat") is None
    assert linux.windows(None, "CrossChat") == []                                 # no browser: no windows
    assert linux.work_area() == linux.SCREEN
    launched = []

    class Started:
        def __init__(self, command, **kw):
            launched.append((command, kw))

        def wait(self):
            return 0

    monkeypatch.setattr(linux.subprocess, "Popen", Started)
    handle = asyncio.run(linux.open_app("/usr/bin/google-chrome", "http://127.0.0.1:4466/", (10, 20, 300, 400)))
    assert handle is None
    command, kw = launched[0]
    assert command == ["/usr/bin/google-chrome", "--app=http://127.0.0.1:4466/", "--window-position=10,20", "--window-size=300,400"]
    assert kw["start_new_session"] and kw["stdin"] == linux.subprocess.DEVNULL     # the browser outlives the hub
    linux.place(None, 0, 0, 1, 1)                                                 # nothing to move or close: nothing happens
    linux.close(None)


def test_the_new_window_is_found_and_placed(monkeypatch):
    answers = iter([[11, 12], [11, 12], [11, 12, 99]])
    placed = []
    monkeypatch.setattr(linux, "windows", lambda app, prefix=None: next(answers))
    monkeypatch.setattr(linux, "place", lambda handle, *where: placed.append((handle, where)))
    monkeypatch.setattr(linux.subprocess, "Popen", lambda command, **kw: type("P", (), {"wait": lambda self: 0})())
    handle = asyncio.run(linux.open_app("/usr/bin/chromium", "http://127.0.0.1:4466/", (1, 2, 3, 4)))
    assert handle == 99 and placed == [(99, (1, 2, 3, 4))]


def test_message_boxes_use_the_desktops_own_tool(monkeypatch):
    shown = []
    monkeypatch.setattr(linux.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(linux.subprocess, "run", lambda command, **kw: shown.append(command))
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    linux.message_box("hello")
    assert shown == []                                                           # no desktop: nobody to tell
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    linux.message_box("<b>not markup</b>")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    linux.message_box("hi")
    assert shown[0] == ["kdialog", "--title", "CrossChat", "--sorry", "<b>not markup</b>"]
    assert shown[1][:3] == ["zenity", "--warning", "--no-markup"] and shown[1][-1] == "--text=hi"


@linux_only                                       # (os.kill on Windows ends the process, whatever the signal)
def test_a_running_process_is_seen():
    assert linux.running(os.getpid())
    assert not linux.running(2 ** 22 + 12345)


def test_on_wayland_an_open_chat_window_is_not_opened_twice(home, monkeypatch):
    """A Wayland browser's windows are out of X's sight: when a chat window is connected, "Open chat" opens no other."""
    home(None)
    monkeypatch.setattr(hub, "LINUX", True)
    monkeypatch.setattr(hub, "MAC", False)
    monkeypatch.setattr(hub, "linux", linux, raising=False)
    monkeypatch.setattr(linux, "windows", lambda app, prefix=None: None)
    monkeypatch.setattr(linux, "browser", lambda want: "/usr/bin/google-chrome")
    monkeypatch.setattr(linux, "work_area", lambda: (0, 0, 1920, 1080))
    opened = []

    async def open_app(url, where, role=None):
        opened.append((url, where))
    monkeypatch.setattr(hub, "open_app", open_app)
    asyncio.run(hub.show_window())
    assert len(opened) == 1 and opened[0][1] == (1460, 0, 460, 1080)              # none open yet: one opens, at the right edge
    hub.roles["speaker"].append(object())                                        # the chat window connected
    try:
        asyncio.run(hub.show_window())
    finally:
        hub.roles["speaker"].clear()
    assert len(opened) == 1


@linux_only
def test_the_hub_does_its_jobs_the_linux_way(home, monkeypatch, tmp_path):
    home(None)
    assert hub.LINUX and not hub.MAC
    left, top, right, bottom = hub.work_area()
    assert right > left and bottom > top
    assert hub.obs_open(os.getpid()) and not hub.obs_open(2 ** 22 + 12345)
    assert hub.network_category("192.168.1.20") == ""
    assert isinstance(hub.browser_windows("CrossChat"), list)
    folder = tmp_path / "obs-studio" / "plugin_config" / "obs-websocket"
    folder.mkdir(parents=True)
    (folder / "config.json").write_text('{"server_port": 4999, "server_password": "pw", "server_enabled": true}')
    monkeypatch.setattr(linux, "OBS_SETTINGS", str(tmp_path / "obs-studio"))
    assert hub.obs_settings() == {"host": "127.0.0.1", "port": 4999, "password": "pw", "enabled": True}


# ---- Tailscale on Linux: only the address of Tailscale's own interface, while it's up ----------------------------
UP = tailscale.IFF_UP | tailscale.IFF_RUNNING


def test_tailscale_on_linux_counts_only_its_own_interface_when_up():
    assert tailscale.linux_address([("tailscale0", "100.101.102.103", UP)]) == "100.101.102.103"
    assert tailscale.linux_address([("tailscale0", "100.101.102.103", tailscale.IFF_UP)]) == ""   # up, but not running
    assert tailscale.linux_address([("tailscale0", "192.168.1.5", UP)]) == ""                    # not Tailscale's range
    assert tailscale.linux_address([]) == ""                                                     # not installed


def test_on_linux_the_address_comes_from_the_interfaces_never_from_a_program(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(tailscale, "linux_interfaces", lambda: [("tailscale0", "100.64.0.9", UP)])

    def nothing_runs(*a, **k):
        raise AssertionError("no program is run on Linux")

    assert tailscale.address(nothing_runs) == "100.64.0.9"

    def broken():
        raise OSError("no sockets")

    monkeypatch.setattr(tailscale, "linux_interfaces", broken)
    assert tailscale.address(nothing_runs) == ""


@linux_only
def test_on_linux_only_interfaces_named_tailscale_are_asked():
    names = [name for _, name in socket.if_nameindex()]
    found = tailscale.linux_interfaces()
    assert all(name.startswith("tailscale") and name in names for name, _, _ in found)


# ---- a real window, under X ----------------------------------------------------------------------------------------
def throwaway_browser(tmp_path):
    """A program that starts this computer's Chrome or Chromium with a profile of its own (never the person's)."""
    real = linux.browser("chrome") or linux.browser("chromium")
    if not real:
        return None
    wrapper = tmp_path / "browser"
    wrapper.write_text('#!/bin/sh\nexec "%s" --user-data-dir="%s" --no-first-run --no-default-browser-check --disable-gpu '
                       '--password-store=basic --enable-logging=stderr "$@" 2>"%s"\n' % (real, tmp_path / "profile", tmp_path / "browser.log"))
    wrapper.chmod(0o755)
    return str(wrapper)


def browser_log(tmp_path):
    try:
        return (tmp_path / "browser.log").read_text(errors="replace")[-4000:]
    except OSError:
        return "(no log)"


def what_x_shows():
    """Every top-level window X knows, for a test that couldn't find the browser's."""
    import ctypes
    with linux._display() as (lib, display):
        parent, children, count = ctypes.c_ulong(), ctypes.c_void_p(), ctypes.c_uint()
        lib.XQueryTree(display, lib.XDefaultRootWindow(display), ctypes.byref(ctypes.c_ulong()), ctypes.byref(parent), ctypes.byref(children),
                       ctypes.byref(count))
        found = list((ctypes.c_ulong * count.value).from_address(children.value)) if children.value else []
        return [(hex(w), linux._property(lib, display, w, "WM_CLASS"), linux._title(lib, display, w), linux._shown(lib, display, w)) for w in found]


@linux_only
@pytest.mark.skipif(os.environ.get("CROSSCHAT_WINDOW_TESTS") != "1" or not os.environ.get("DISPLAY"),
                    reason="opens a real browser window: set CROSSCHAT_WINDOW_TESTS=1 and run it on an X display (xvfb-run)")
def test_a_real_browser_window_opens_moves_and_closes(tmp_path):
    browser = throwaway_browser(tmp_path)
    if not browser:
        pytest.skip("no Chrome or Chromium here")
    page = tmp_path / "page.html"
    page.write_text("<!doctype html><title>CrossChat window test</title><p>hello")
    started = time.monotonic()
    handle = asyncio.run(linux.open_app(browser, page.as_uri(), (40, 50, 420, 500)))
    print("the new window was found %.1f s after the browser was started" % (time.monotonic() - started))   # (a cold start took 10)
    try:
        assert handle, "the new window wasn't found\nX shows: %r\nthe browser said:\n%s" % (what_x_shows(), browser_log(tmp_path))
        assert what_x_shows() and browser_log(tmp_path) != "(no log)"     # the report above must work when it's needed
        deadline = time.time() + 15
        while time.time() < deadline and not linux.windows(browser, "CrossChat window test"):
            time.sleep(0.25)
        assert linux.windows(browser, "CrossChat window test") == [handle]
        left, top, right, bottom = linux.work_area()
        assert right > left and bottom > top
        linux._move(handle, 100, 120, 400, 300)
        time.sleep(1)
        assert geometry(handle)[2:] == (400, 300)
        linux._close(handle)
        deadline = time.time() + 15
        while time.time() < deadline and linux.windows(browser, "CrossChat window test"):
            time.sleep(0.25)
        assert linux.windows(browser, "CrossChat window test") == []
    finally:
        os.system("pkill -f -- '--user-data-dir=%s' >/dev/null 2>&1" % (tmp_path / "profile"))
        shutil.rmtree(tmp_path / "profile", ignore_errors=True)


def geometry(handle):
    """(x, y, width, height) of a window, as X has it."""
    import ctypes
    with linux._display() as (lib, display):
        lib.XGetGeometry.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)] + [ctypes.POINTER(ctypes.c_int)] * 2 \
            + [ctypes.POINTER(ctypes.c_uint)] * 4
        root, x, y = ctypes.c_ulong(), ctypes.c_int(), ctypes.c_int()
        width, height, border, depth = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
        lib.XGetGeometry(display, handle, ctypes.byref(root), ctypes.byref(x), ctypes.byref(y), ctypes.byref(width), ctypes.byref(height),
                         ctypes.byref(border), ctypes.byref(depth))
        return x.value, y.value, width.value, height.value
