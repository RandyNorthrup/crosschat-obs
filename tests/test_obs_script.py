"""The OBS script (obs/crosschat.lua) run in LuaJIT, the Lua OBS uses, with a stand-in for OBS's own functions.

It starts a stand-in hub.py through the script's real code (ShellExecuteExW on Windows, posix_spawn on a Mac) and
checks the watchdog: a hub that stops with an error is started again, at most five times in ten minutes, and one that
ends normally is left alone. The scenario itself is tests/obs_script_driver.lua. It runs inside this process with
lupa (pip install lupa) where lupa has LuaJIT (Windows, Linux), else with a `luajit` program (brew install luajit on a
Mac); without either the tests are skipped.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "obs", "crosschat.lua")
DRIVER = os.path.join(ROOT, "tests", "obs_script_driver.lua")
try:
    from lupa import luajit21
except ImportError:
    luajit21 = None
LUAJIT = shutil.which("luajit")
pytestmark = pytest.mark.skipif(not (luajit21 or LUAJIT), reason="needs LuaJIT: pip install lupa, or brew install luajit")
FAKE = """import json, os, sys
app = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
held = []                                       # the files this program was handed open (a Mac can name them)
if sys.platform == "darwin":
    import fcntl
    for fd in range(3, 256):
        try:
            held.append(fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024)).rstrip(b"\\0").decode())
        except OSError:
            pass
with open(os.path.join(app, "NAME.held.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps(held) + "\\n")
with open(os.path.join(app, "NAME.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
with open(os.path.join(app, "exit_code.txt"), encoding="utf-8") as f:
    sys.exit(int(f.read()))
"""


@pytest.fixture
def obs(tmp_path):
    """run(...) loads the script as OBS would, in an installed-looking CrossChat folder with stand-ins for hub.py and
    control.py that end with `exit_code`, and plays one scenario; then .runs(), .log and .report tell what happened."""
    app = tmp_path / "Cross Chat"                       # a space in the path, like "Application Support"
    (app / "hub").mkdir(parents=True)
    (app / "obs").mkdir()
    for name in ("hub", "control"):
        (app / "hub" / (name + ".py")).write_text(FAKE.replace("NAME", name), encoding="utf-8")
    python = ""
    if sys.platform == "win32":
        windowless = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        python = windowless if os.path.exists(windowless) else sys.executable
    else:                                               # the installer's own Python, where the script looks for it
        (app / ".venv" / "bin").mkdir(parents=True)
        os.symlink(sys.executable, app / ".venv" / "bin" / "python3")

    class Obs:
        report, log = [], []

        def run(self, exit_code=0, press="", wait_for="", runs=1, seconds=20, extra=0):
            (app / "exit_code.txt").write_text(str(exit_code), encoding="utf-8")
            given = [SCRIPT, str(app / "obs").replace("\\", "/") + "/", python, press, wait_for, str(runs), str(seconds), str(extra)]
            if luajit21:
                lua = luajit21.LuaRuntime()
                for name, value in zip(("SCRIPT", "APP_OBS", "PYTHON", "PRESS", "WAIT_FOR", "RUNS", "SECONDS", "EXTRA"), given, strict=True):
                    lua.globals()[name] = value
                with open(DRIVER, encoding="utf-8") as f:
                    lua.execute(f.read())
                self.report = list(lua.eval("REPORT").values())
            else:
                done = subprocess.run([LUAJIT, DRIVER, *given], capture_output=True, text=True, timeout=seconds + extra + 60)
                assert done.returncode == 0, done.stderr
                self.report = done.stdout.splitlines()
            self.log = [line[4:] for line in self.report if line.startswith("LOG ")]

        def runs(self, name="hub"):
            try:
                with open(app / (name + ".jsonl"), encoding="utf-8") as f:
                    return [json.loads(line) for line in f]
            except FileNotFoundError:
                return []

        def held(self, name="hub"):
            """For each run of `name`: the files it was handed open."""
            return self.runs(name + ".held")

    return Obs()


def test_the_script_starts_the_hub_for_this_obs(obs):
    obs.run()
    folder = os.path.join(os.environ.get("APPDATA", ""), "obs-studio") if sys.platform == "win32" else \
        os.path.expanduser("~/Library/Application Support/obs-studio")
    pid = os.getpid() if luajit21 else None              # (the luajit program is OBS here, with its own pid)
    first = obs.runs()[0]
    assert first[0] == "--obs-pid" and first[1].isdigit() and first[2:] == ["--obs-config", folder]
    assert pid is None or first[1] == str(pid)


def test_a_hub_that_ends_normally_is_left_alone(obs):
    obs.run(extra=3)
    assert len(obs.runs()) == 1 and not any("starting it again" in line for line in obs.log)


def test_the_watchdog_restarts_a_failing_hub_five_times_then_gives_up(obs):
    obs.run(exit_code=3, wait_for="keeps stopping", seconds=60, extra=2)
    assert any("keeps stopping" in line for line in obs.log)
    assert sum("code 3" in line for line in obs.log) == 5
    assert len(obs.runs()) == 6                          # the first start and five more


def test_buttons_run_control_py(obs):
    obs.run(press="show")
    assert obs.runs("control") == [["show"]]


@pytest.mark.skipif(sys.platform != "darwin", reason="a Mac matter: on Windows the hub is started without OBS's handles")
def test_the_hub_gets_none_of_obs_own_files_or_sockets(obs):
    # A hub holding OBS's WebSocket server socket kept OBS's port taken after OBS closed (found with OBS 33 on macOS 15)
    obs.run(press="show")
    for name in ("hub", "control"):
        held = obs.held(name)
        assert held and not any(path.endswith("obs-held.txt") for paths in held for path in paths), held


@pytest.mark.skipif(sys.platform == "win32", reason="zombie processes are a Unix matter")
def test_finished_programs_are_collected(obs):
    obs.run(press="show", extra=2)                       # a few watchdog rounds after hub.py and control.py ended
    assert "CHILDREN none" in obs.report
