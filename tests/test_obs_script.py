"""The OBS script (obs/crosschat.lua) run in LuaJIT, the Lua OBS uses, with a stand-in for OBS's own functions.

It starts a stand-in hub.py through the script's real code (ShellExecuteExW on Windows, posix_spawn on a Mac or Linux) and
checks the watchdog: a hub that stops with an error is started again, at most five times in ten minutes, and one that
ends normally is left alone. The scenario itself is tests/obs_script_driver.lua. It runs inside this process with
lupa (pip install lupa) where lupa has LuaJIT (Windows, Linux), else with a `luajit` program (brew install luajit on a
Mac); without either the tests are skipped. Alert boxes are stood in for, so none appears: on Windows by the driver, on
a Mac or Linux by stand-ins for osascript and zenity first on the PATH.
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
FAKE = """import json, os, sys, time
app = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
held = []                                       # the files this program was handed open (a Mac or Linux can name them)
if sys.platform == "darwin":
    import fcntl
    for fd in range(3, 256):
        try:
            held.append(fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024)).rstrip(b"\\0").decode())
        except OSError:
            pass
elif sys.platform.startswith("linux"):
    for fd in range(3, 256):
        try:
            held.append(os.readlink("/proc/self/fd/%d" % fd))
        except OSError:
            pass
with open(os.path.join(app, "NAME.held.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps(held) + "\\n")
with open(os.path.join(app, "NAME.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
with open(os.path.join(app, "NAME.jsonl"), encoding="utf-8") as f:
    run = sum(1 for _ in f) - 1                 # which start of this program this is: it plays that entry of the plan
with open(os.path.join(app, "plan.json"), encoding="utf-8") as f:
    plan = json.load(f)
code, stay = plan[min(run, len(plan) - 1)]
time.sleep(stay)
sys.exit(code)
"""
STAND_IN = """#!/bin/sh
for each in "$@"; do printf '%s\\n' "$each"; done >> "$CROSSCHAT_TEST_ALERTS"
"""


@pytest.fixture
def obs(tmp_path, monkeypatch):
    """run(...) loads the script as OBS would, in an installed-looking CrossChat folder with stand-ins for hub.py and
    control.py that end with `exit_code`, or follow `plan` ([[exit code, seconds to stay]]: the first start, the second,
    ..., the last repeating), and plays one scenario; then .runs(), .log, .report, .description and .alerts() tell what
    happened."""
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
        tools = tmp_path / "bin"                        # what a real alert would show comes here instead
        tools.mkdir()
        for tool in ("osascript", "zenity"):
            (tools / tool).write_text(STAND_IN, encoding="utf-8")
            (tools / tool).chmod(0o755)
        monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.environ["PATH"])
        monkeypatch.setenv("CROSSCHAT_TEST_ALERTS", str(tmp_path / "alerts.txt"))

    class Obs:
        report, log = [], []
        description = ""

        def run(self, exit_code=0, press="", wait_for="", runs=1, seconds=20, extra=0, plan=None, port=None, python_setting=None):
            (app / "plan.json").write_text(json.dumps(plan or [[exit_code, 0]]), encoding="utf-8")
            if port:
                (app / "config.json").write_text(json.dumps({"port": port}), encoding="utf-8")
            given = [SCRIPT, str(app / "obs").replace("\\", "/") + "/", python if python_setting is None else python_setting, press, wait_for,
                     str(runs), str(seconds), str(extra)]
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
            self.description = next(line[12:] for line in self.report if line.startswith("DESCRIPTION "))

        def alerts(self):
            """The boxes the script would have shown, each as one string."""
            if sys.platform == "win32":
                return [line[6:] for line in self.report if line.startswith("ALERT ")]
            try:
                with open(tmp_path / "alerts.txt", encoding="utf-8") as f:
                    said = f.read().splitlines()
            except FileNotFoundError:
                return []
            return [" ".join(said)] if said else []

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


def obs_folder():
    """Where OBS keeps its settings on this system (where the script tells the hub to look)."""
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA", ""), "obs-studio")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/obs-studio")
    base = os.environ.get("XDG_CONFIG_HOME", "")
    return os.path.join(base if base.startswith("/") else os.path.expanduser("~/.config"), "obs-studio")


def test_the_script_starts_the_hub_for_this_obs(obs):
    obs.run()
    folder = obs_folder()
    pid = os.getpid() if luajit21 else None              # (the luajit program is OBS here, with its own pid)
    first = obs.runs()[0]
    assert first[0] == "--obs-pid" and first[1].isdigit() and first[2:] == ["--obs-config", folder]
    assert pid is None or first[1] == str(pid)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="XDG folders are a Linux matter")
def test_on_linux_the_script_finds_obs_settings_where_obs_does(obs, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "elsewhere"))      # (what a Flatpak or a custom setup sets)
    obs.run()
    assert obs.runs()[0][2:] == ["--obs-config", str(tmp_path / "elsewhere" / "obs-studio")]


def test_a_hub_that_ends_normally_is_left_alone(obs):
    obs.run(extra=3)
    assert len(obs.runs()) == 1 and not any("starting it again" in line for line in obs.log)


def test_the_watchdog_restarts_a_failing_hub_five_times_then_gives_up(obs):
    obs.run(exit_code=7, wait_for="keeps stopping", seconds=60, extra=2)  # (not code 3: that means another hub is running)
    assert any("keeps stopping" in line for line in obs.log)
    assert sum("code 7" in line for line in obs.log) == 5
    assert len(obs.runs()) == 6                          # the first start and five more
    assert len(obs.alerts()) == 1 and "keeps stopping" in obs.alerts()[0]    # a box too: few people open the script log


def test_a_hub_that_finds_another_one_running_is_left_alone(obs):
    obs.run(exit_code=3, extra=2)
    assert len(obs.runs()) == 1 and not any("starting it again" in line for line in obs.log)
    assert any("already running" in line for line in obs.log) and obs.alerts() == []


def test_starting_the_hub_again_keeps_watching_the_running_one(obs):
    # The first hub is up; the button's hub finds it and leaves with code 3. The first one is still the one watched:
    # when it crashes it is started again, and the button's hub was never a crash.
    obs.run(plan=[[7, 3], [3, 0], [0, 0]], press="restart", wait_for="code 7", runs=3, seconds=30, extra=1)
    assert len(obs.runs()) == 3
    assert any("already running" in line for line in obs.log)
    assert sum("starting it again" in line for line in obs.log) == 1 and not any("code 3" in line for line in obs.log)


def test_the_hub_started_again_takes_over_when_the_first_one_has_ended(obs):
    # The first hub ends by itself just after the button was pressed; the new one stays and is the one watched.
    obs.run(plan=[[0, 1], [7, 4], [0, 0]], press="restart", wait_for="code 7", runs=3, seconds=30, extra=1)
    assert len(obs.runs()) == 3 and sum("starting it again" in line for line in obs.log) == 1


def test_no_python_shows_a_box_not_just_a_log_line(obs, tmp_path):
    missing = str(tmp_path / "no-such-python")
    obs.run(python_setting=missing, press="show", wait_for="could not start Python", runs=0, extra=1)
    assert obs.runs() == [] and obs.runs("control") == []
    assert sum("could not start Python" in line for line in obs.log) == 2     # the hub, then the button: both logged,
    assert len(obs.alerts()) == 1 and "could not start Python" in obs.alerts()[0] and missing in obs.alerts()[0]  # one box


def test_buttons_run_control_py(obs):
    obs.run(press="show")
    assert obs.runs("control") == [["show"]]


def test_the_theme_studio_button_asks_control_py_which_reads_the_port(obs):
    obs.run(press="studio")
    assert obs.runs("control") == [["studio"]]


def test_the_links_shown_in_obs_use_the_port_from_config_json(obs):
    obs.run(port=5151)
    assert "http://127.0.0.1:5151/overlay/chat" in obs.description and "/overlay/alerts" in obs.description
    assert "4466" not in obs.description


def test_the_links_use_the_default_port_without_a_config_json(obs):
    obs.run()
    assert "http://127.0.0.1:4466/overlay/chat" in obs.description


@pytest.mark.skipif(sys.platform == "win32", reason="a Mac and Linux matter: on Windows the hub is started without OBS's handles")
def test_the_hub_gets_none_of_obs_own_files_or_sockets(obs):
    # A hub holding OBS's WebSocket server socket kept OBS's port taken after OBS closed (found with OBS 33 on macOS 15;
    # on Linux, posix_spawn passes them too unless the script closes them)
    obs.run(press="show")
    for name in ("hub", "control"):
        held = obs.held(name)
        assert held and not any(path.endswith("obs-held.txt") for paths in held for path in paths), held


@pytest.mark.skipif(sys.platform == "win32", reason="zombie processes are a Unix matter")
def test_finished_programs_are_collected(obs):
    obs.run(press="show", extra=2)                       # a few watchdog rounds after hub.py and control.py ended
    assert "CHILDREN none" in obs.report
