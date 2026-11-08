"""The installers' and uninstallers' behaviour, run for real on folders of the test's own: never this computer's CrossChat,
Start menu, Documents or keyring. uninstall.ps1 and steps.ps1 are told where to work; uninstall.sh has stand-ins for its
keyring tools first on the PATH and a home folder of its own. (On Windows, install.sh and uninstall.sh run in Git's bash,
which they take for a Mac.)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOWS = sys.platform == "win32"
LINUX = sys.platform.startswith("linux")
windows_only = pytest.mark.skipif(not WINDOWS, reason="the Windows uninstaller")
SETTINGS = ["config.json", "quick.json", "filters.json", "tts.json"]


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def find_bash():
    if not WINDOWS:
        return shutil.which("bash")
    # bash on PATH may be WSL's, a different computer; Git's bin\bash.exe puts its own tools before the test's stand-ins
    git = shutil.which("git")
    bash = os.path.join(os.path.dirname(os.path.dirname(git)), "usr", "bin", "bash.exe") if git else ""
    return bash if os.path.exists(bash) else None


BASH = find_bash()
needs_bash = pytest.mark.skipif(not BASH, reason="no bash here")


def installed(app):
    """A CrossChat folder with some of everything in it."""
    (app / "hub").mkdir(parents=True)
    (app / "scripts").mkdir()
    (app / "themes").mkdir()
    (app / "logs").mkdir()
    (app / "hub" / "hub.py").write_text("", encoding="utf-8")
    (app / "hub" / "control.py").write_text("", encoding="utf-8")
    for name in SETTINGS:
        (app / name).write_text('{"mine": true}', encoding="utf-8")
    (app / "themes" / "mine.json").write_text("{}", encoding="utf-8")
    (app / "logs" / "2026-11-01_1900.jsonl").write_text('{"type": "msg"}\n', encoding="utf-8")
    (app / "twitch.bin").write_text("sealed", encoding="utf-8")


# ---- Windows: scripts/uninstall.ps1, Uninstall.cmd, installer/steps.ps1 ----------------------------------------------
class Windows:
    def __init__(self, tmp_path):
        self.app, self.menu, self.keep = tmp_path / "Cross Chat", tmp_path / "Menu", tmp_path / "Backup"
        installed(self.app)
        (self.menu).mkdir()
        (self.menu / "Open chat.lnk").write_text("", encoding="utf-8")
        for script in ("scripts/uninstall.ps1", "Uninstall.cmd"):
            shutil.copy(os.path.join(ROOT, script), self.app / script)

    @property
    def where(self):
        return ["-App", str(self.app), "-Menu", str(self.menu), "-KeepIn", str(self.keep), "-AppsEntry", "HKCU:\\Software\\CrossChat-test-none"]

    def uninstall(self, *flags, answers=b"", timeout=120):
        script = str(self.app / "scripts" / "uninstall.ps1")
        done = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, *flags, *self.where],
                              input=answers, capture_output=True, timeout=timeout)
        return done.returncode, (done.stdout + done.stderr).decode(errors="replace")


@pytest.fixture
def windows(tmp_path):
    return Windows(tmp_path)


@windows_only
def test_quiet_keeps_the_settings_and_themes_and_says_the_chat_history_goes(windows):
    code, said = windows.uninstall("-Quiet")
    assert code == 0, said
    assert not windows.app.exists() and "CrossChat is removed" in said
    assert sorted(os.listdir(windows.keep)) == sorted([*SETTINGS, "themes"])
    assert "chat history goes" in said.lower() and not (windows.keep / "logs").exists()
    assert not windows.menu.exists()


@windows_only
def test_keeping_the_chat_history_copies_it(windows):
    code, said = windows.uninstall(answers=b"y\ny\ny\n")     # remove it, keep the settings, keep the chat history
    assert code == 0, said
    assert (windows.keep / "logs" / "2026-11-01_1900.jsonl").exists() and not windows.app.exists()


@windows_only
def test_saying_no_to_the_chat_history_says_it_goes(windows):
    code, said = windows.uninstall(answers=b"y\ny\nn\n")
    assert code == 0, said
    assert not (windows.keep / "logs").exists() and "chat history goes" in said.lower()


@windows_only
def test_a_file_in_use_for_a_moment_does_not_stop_it(windows):
    held = open(windows.app / "logs" / "in-use.txt", "w")      # (a program that has just ended, an antivirus scan)

    def let_go():                                         # once the backup is done the folder goes next: the first try meets this
        while not (windows.keep / "tts.json").exists():
            time.sleep(0.02)
        time.sleep(1)
        held.close()

    threading.Thread(target=let_go, daemon=True).start()
    code, said = windows.uninstall("-Quiet")
    assert code == 0, said
    assert not windows.app.exists() and "CrossChat is removed" in said


@windows_only
def test_a_folder_that_stays_is_reported_and_not_called_removed(windows):
    with open(windows.app / "logs" / "in-use.txt", "w"):
        code, said = windows.uninstall("-Quiet")
    assert code == 1, said
    assert windows.app.exists() and "could not be fully removed" in said and "CrossChat is removed" not in said


@windows_only
def test_the_hub_is_stopped_for_good_before_the_folder_goes(windows):
    # As OBS starts it: running from the folder, with a file open in it. It stops; nothing else on this PC does.
    (windows.app / "hub" / "hub.py").write_text("import os, sys, time\nopen(os.path.join(sys.argv[1], 'held.txt'), 'w')\n"
                                                "print('up', flush=True)\ntime.sleep(60)\n", encoding="utf-8")
    hub = subprocess.Popen([sys.executable, str(windows.app / "hub" / "hub.py"), str(windows.app / "logs")], cwd=windows.app / "hub",
                           stdout=subprocess.PIPE)
    try:
        assert hub.stdout.readline().strip() == b"up"
        code, said = windows.uninstall("-Quiet")
        assert code == 0, said
        assert hub.wait(10) is not None and not windows.app.exists()
    finally:
        hub.kill()


@windows_only
def test_uninstall_cmd_removes_the_folder_it_runs_from(windows):
    # The Start-menu shortcut starts Uninstall.cmd with the CrossChat folder as the folder it works in.
    line = '""%s" -Quiet %s"' % (windows.app / "Uninstall.cmd", " ".join('"%s"' % part for part in windows.where))
    done = subprocess.run("cmd.exe /c " + line, cwd=windows.app, input=b"\r\n", capture_output=True, timeout=120)
    said = (done.stdout + done.stderr).decode(errors="replace")
    assert not windows.app.exists(), said
    assert "CrossChat is removed" in said and "cannot be found" not in said


@windows_only
@pytest.mark.parametrize("flags, kept", [(["-Backup"], [*SETTINGS, "themes"]), (["-Backup", "-BackupLogs"], [*SETTINGS, "themes", "logs"]),
                                         ([], None)])
def test_setups_uninstall_step_keeps_what_it_is_told_to(windows, flags, kept):
    done = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(ROOT, "installer", "steps.ps1"),
                           "-Step", "uninstall", "-App", str(windows.app), "-KeepIn", str(windows.keep), *flags], capture_output=True, timeout=120)
    assert done.returncode == 0, done.stderr
    if kept is None:
        assert not windows.keep.exists()
    else:
        assert sorted(os.listdir(windows.keep)) == sorted(kept)


# ---- macOS and Linux: scripts/uninstall.sh ---------------------------------------------------------------------------
class Shell:
    def __init__(self, tmp_path):
        self.home = tmp_path / "home"
        self.keep = self.home / "Documents" / "CrossChat backup"
        self.app = (self.home / ".local" / "share" / "CrossChat") if LINUX else (self.home / "Library" / "Application Support" / "CrossChat")
        installed(self.app)
        shutil.copy(os.path.join(ROOT, "scripts", "uninstall.sh"), self.app / "scripts" / "uninstall.sh")
        self.tools = tmp_path / "tools"
        self.tools.mkdir()
        for tool in ("secret-tool", "security"):
            self.tool(tool, "#!/bin/sh\nexit 0\n")
        self.tool("xdg-user-dir", '#!/bin/sh\nprintf \'%s/Documents\\n\' "$HOME"\n')

    def tool(self, name, text):
        path = self.tools / name
        path.write_text(text, encoding="utf-8", newline="\n")
        path.chmod(0o755)

    def env(self):
        env = {k: v for k, v in os.environ.items() if k not in ("XDG_DATA_HOME", "XDG_CONFIG_HOME")}
        env.update(HOME=str(self.home), PATH=os.pathsep.join([str(self.tools), os.path.dirname(BASH), os.environ["PATH"]]))
        return env

    def uninstall(self, *flags):
        done = subprocess.run([BASH, str(self.app / "scripts" / "uninstall.sh"), *flags], env=self.env(), capture_output=True, timeout=120)
        return done.returncode, (done.stdout + done.stderr).decode(errors="replace")


@pytest.fixture
def shell(tmp_path):
    return Shell(tmp_path)


@needs_bash
def test_the_shell_uninstaller_keeps_all_the_settings_windows_keeps(shell):
    code, said = shell.uninstall("--quiet")
    assert code == 0, said
    assert sorted(os.listdir(shell.keep)) == sorted([*SETTINGS, "themes"])
    assert not shell.app.exists() and "CrossChat is removed" in said


@needs_bash
def test_the_shell_uninstaller_says_the_chat_history_goes(shell):
    code, said = shell.uninstall("--quiet")
    assert code == 0, said
    assert "chat history goes" in said.lower() and not (shell.keep / "logs").exists()


@needs_bash
def test_the_shell_uninstaller_says_when_the_folder_stays(shell):
    shell.tool("rm", "#!/bin/sh\nexit 0\n")              # a folder rm can't take away
    code, said = shell.uninstall("--quiet")
    assert code == 1, said
    assert shell.app.exists() and "could not be fully removed" in said and "CrossChat is removed" not in said


@pytest.mark.skipif(WINDOWS, reason="a real terminal: on a Mac or Linux")
@pytest.mark.parametrize("answer, kept", [(b"y", True), (b"n", False), (b"", True)])
def test_the_shell_uninstaller_asks_about_the_chat_history(shell, answer, kept):
    """In a terminal of its own, as read </dev/tty needs: remove it, keep the settings, then the chat history."""
    import pty
    import select
    pid, terminal = pty.fork()
    if pid == 0:
        os.execve(BASH, [BASH, str(shell.app / "scripts" / "uninstall.sh")], shell.env())
    os.write(terminal, b"y\ny\n" + answer + b"\n")
    said, deadline = b"", time.time() + 60
    while time.time() < deadline:
        if not select.select([terminal], [], [], deadline - time.time())[0]:
            break
        try:
            chunk = os.read(terminal, 4096)
        except OSError:                                   # (Linux: the script has ended)
            break
        if not chunk:
            break
        said += chunk
    _, status = os.waitpid(pid, 0)
    os.close(terminal)
    assert os.waitstatus_to_exitcode(status) == 0, said
    assert (shell.keep / "logs" / "2026-11-01_1900.jsonl").exists() == kept
    assert not shell.app.exists()


# ---- every uninstaller keeps the same things; every installer asks the same questions --------------------------------
def test_every_uninstaller_keeps_the_same_settings():
    def kept(text):
        line = re.search(r"(?:item in |\(|\+= )'?config\.json.*", text).group(0)
        return re.findall(r"\bthemes\b|[\w-]+\.json", line)

    lists = [kept(read(name)) for name in ("scripts/uninstall.sh", "scripts/uninstall.ps1", "installer/steps.ps1")]
    assert lists[0] == lists[1] == lists[2] == ["config.json", "themes", "quick.json", "filters.json", "tts.json"]


def section(text, start, end):
    return text.split(start, 1)[1].split(end, 1)[0]


def test_the_mac_and_linux_installer_asks_what_windows_asks():
    windows = section(read("scripts/install.ps1"), "# ---- your channels", "# ---- OBS")
    posix = section(read("scripts/install.sh"), "# ---- your channels", "# ---- OBS")

    def questions(text, function):
        said = []
        for found in re.finditer(r"\b(?:%s) (?:'((?:[^']|'')*)'|\"([^\"]*)\")" % function, text):
            said.append((found.group(1) or found.group(2)).replace("''", "'"))
        return said

    assert questions(posix, "ask|confirm") == questions(windows, "Ask|Yes")
    assert sorted(set(re.findall(r"CROSSCHAT_(\w+)=", posix))) == sorted(set(re.findall(r"\$env:CROSSCHAT_(\w+) =", windows)))


def test_the_mac_and_linux_installer_says_what_windows_says_about_privacy():
    windows = section(read("scripts/install.ps1"), "# ---- privacy", "# ---- your channels")
    posix = section(read("scripts/install.sh"), "# ---- privacy", "# ---- your channels")

    def sentences(text):
        return [line.replace("''", "'").replace("$MACHINE", "PC") for line in re.findall(r"(?im)^say ['\"](.*)['\"]\s*$", text)]

    assert sentences(posix) == sentences(windows)


@needs_bash
def test_the_mac_and_linux_installer_saves_instagram_and_the_update_notice(tmp_path):
    # Its questions, from the real script, as a person answering yes to each.
    app = tmp_path / "app"
    (app / "hub").mkdir(parents=True)
    for name in ("setup_config.py", "config_file.py"):        # (the installers copy all of hub/; this needs only these)
        shutil.copy(os.path.join(ROOT, "hub", name), app / "hub" / name)
    shutil.copy(os.path.join(ROOT, "config.example.json"), app / "config.example.json")
    run = tmp_path / "questions.sh"
    run.write_text('set -eo pipefail\nsay() { :; }\nstep() { :; }\nfail() { echo "$1"; exit 1; }\nask() { printf yes; }\nconfirm() { return 0; }\n'
                   'APP="$1"; VENV_PY="$2"\n#' + section(read("scripts/install.sh"), "# ---- your channels ", "# ---- OBS"), encoding="utf-8", newline="\n")
    done = subprocess.run([BASH, str(run), str(app), sys.executable], capture_output=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
    with open(app / "config.json", encoding="utf-8") as f:
        config = json.load(f)
    assert config["instagram"] is True and config["updates"]["check"] is True and config["facebook"] is True
