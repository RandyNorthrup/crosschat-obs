"""The OBS script (obs/crosschat.lua) run in LuaJIT, the Lua OBS uses, with a stand-in for OBS's own functions.

It starts a stand-in hub.py through the script's real code (ShellExecuteExW on Windows, posix_spawn on a Mac) and
checks the watchdog: a hub that stops with an error is started again, at most five times in ten minutes, and one that
ends normally is left alone. Needs lupa (pip install lupa); skipped without it.
"""
import json
import os
import sys
import time

import pytest

luajit = pytest.importorskip("lupa.luajit21")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "obs", "crosschat.lua")
FAKE = """import json, os, sys
app = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(app, "%s.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
with open(os.path.join(app, "exit_code.txt"), encoding="utf-8") as f:
    sys.exit(int(f.read()))
"""
OBS = """
log_lines, timers, buttons = {}, {}, {}
obslua = {
  LOG_INFO = 300, LOG_WARNING = 200, OBS_PATH_FILE = 0,
  script_log = function(level, text) table.insert(log_lines, text) end,
  timer_add = function(fn, ms) timers[1] = fn end,
  timer_remove = function(fn) timers[1] = nil end,
  obs_data_get_string = function(settings, key) return PYTHON end,
  obs_hotkey_register_frontend = function() return 1 end,
  obs_data_get_array = function() return nil end,
  obs_hotkey_load = function() end,
  obs_data_array_release = function() end,
  obs_properties_create = function() return {} end,
  obs_properties_add_button = function(props, name, text, callback) buttons[name] = callback end,
  obs_properties_add_path = function() return {} end,
  obs_property_set_long_description = function() end,
}
function script_path() return APP_OBS end
"""


@pytest.fixture
def obs(tmp_path, request):
    """The script loaded as OBS would, in an installed-looking CrossChat folder with stand-ins for hub.py and control.py
    (they end with the exit code the test is marked with: @pytest.mark.exit_code(3))."""
    app = tmp_path / "Cross Chat"                       # a space in the path, like "Application Support"
    (app / "hub").mkdir(parents=True)
    (app / "obs").mkdir()
    for name in ("hub", "control"):
        (app / "hub" / (name + ".py")).write_text(FAKE % name, encoding="utf-8")
    marker = request.node.get_closest_marker("exit_code")
    (app / "exit_code.txt").write_text(str(marker.args[0] if marker else 0), encoding="utf-8")
    python = ""
    if sys.platform == "win32":
        windowless = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        python = windowless if os.path.exists(windowless) else sys.executable
    else:                                               # the installer's own Python, where the script looks for it
        (app / ".venv" / "bin").mkdir(parents=True)
        os.symlink(sys.executable, app / ".venv" / "bin" / "python3")
    lua = luajit.LuaRuntime(unpack_returned_tuples=True)
    lua.globals().APP_OBS = str(app / "obs").replace("\\", "/") + "/"
    lua.globals().PYTHON = python
    lua.execute(OBS)
    with open(SCRIPT, encoding="utf-8") as f:
        lua.execute(f.read())

    class Obs:
        folder = app

        def runs(self, name="hub"):
            try:
                with open(app / (name + ".jsonl"), encoding="utf-8") as f:
                    return [json.loads(line) for line in f]
            except FileNotFoundError:
                return []

        def tick(self, seconds, until=lambda: False):
            end = time.time() + seconds
            while time.time() < end and not until():
                time.sleep(0.2)
                timer = lua.eval("timers[1]")
                if timer:
                    timer()

        def log(self):
            return list(lua.eval("log_lines").values())

    lua.globals().script_load(None)
    yield Obs(), lua
    lua.globals().script_unload()


def test_the_script_starts_the_hub_for_this_obs(obs):
    o, _ = obs
    o.tick(15, until=lambda: o.runs())
    folder = os.path.join(os.environ.get("APPDATA", ""), "obs-studio") if sys.platform == "win32" else \
        os.path.expanduser("~/Library/Application Support/obs-studio")
    assert o.runs()[0] == ["--obs-pid", str(os.getpid()), "--obs-config", folder]


def test_a_hub_that_ends_normally_is_left_alone(obs):
    o, _ = obs
    o.tick(15, until=lambda: o.runs())
    o.tick(3)
    assert len(o.runs()) == 1 and not any("starting it again" in line for line in o.log())


@pytest.mark.exit_code(3)
def test_the_watchdog_restarts_a_failing_hub_five_times_then_gives_up(obs):
    o, _ = obs
    o.tick(60, until=lambda: any("keeps stopping" in line for line in o.log()))
    o.tick(2)
    assert any("keeps stopping" in line for line in o.log())
    assert sum("code 3" in line for line in o.log()) == 5
    assert len(o.runs()) == 6                            # the first start and five more


def test_buttons_run_control_py(obs):
    o, lua = obs
    lua.globals().script_properties()
    lua.eval("buttons.show")(True)
    o.tick(15, until=lambda: o.runs("control"))
    assert o.runs("control") == [["show"]]


@pytest.mark.skipif(sys.platform != "darwin", reason="zombie processes are a Unix matter")
def test_finished_programs_are_collected_on_a_mac(obs):
    o, lua = obs
    lua.globals().script_properties()
    lua.eval("buttons.show")(True)
    o.tick(15, until=lambda: o.runs("control") and o.runs())
    o.tick(2)                                           # a few watchdog rounds collect what has finished
    with pytest.raises(ChildProcessError):              # nothing left over for anyone to collect
        os.waitpid(-1, os.WNOHANG)
