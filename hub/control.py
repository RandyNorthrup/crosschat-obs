"""Ask the running CrossChat hub to do something. The OBS script's buttons and hotkeys and the Start-menu shortcuts use this.

  pythonw control.py show        bring up the chat window (starts the hub first if OBS has not)
  pythonw control.py studio      open the Theme Studio in the browser
  pythonw control.py x-live      go live on X now (only opens X's page when OBS is not streaming)
  pythonw control.py x-private   test: a livestream on X only you can see
  pythonw control.py x-dry       test: fill X's form, never press Go Live
  pythonw control.py unfeature   take the featured message off the stream
  pythonw control.py demo        try CrossChat with a made-up live stream (its own port, nothing is posted anywhere)
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PATHS = {"show": "/show", "x-live": "/x/go?mode=live", "x-private": "/x/go?mode=private", "x-dry": "/x/go?mode=dry",
         "unfeature": "/feature?clear=1"}


def port():
    try:
        with open(os.environ.get("CROSSCHAT_CONFIG") or os.path.join(os.path.dirname(HERE), "config.json"), encoding="utf-8-sig") as f:
            return int(json.load(f).get("port", 4466))
    except (OSError, ValueError, AttributeError):
        return 4466


def start_hub():
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    subprocess.Popen([pythonw if os.path.exists(pythonw) else sys.executable, os.path.join(HERE, "hub.py")], cwd=HERE,
                     creationflags=0x08000008, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


DEMO_PORT = 4477


def main(command):
    base = "http://127.0.0.1:%d" % port()
    if command == "demo":
        demo = "http://127.0.0.1:%d/" % DEMO_PORT
        try:
            urllib.request.urlopen(demo + "version", timeout=2).read()
        except OSError:
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            subprocess.Popen([pythonw if os.path.exists(pythonw) else sys.executable, os.path.join(HERE, "hub.py"), "--demo", "--quiet",
                              "--no-window", "--port", str(DEMO_PORT)], cwd=HERE, creationflags=0x08000008,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)
        os.startfile(demo)
        return 0
    if command == "studio":
        os.startfile(base + "/studio")
        return 0
    if command not in PATHS:
        print(__doc__)
        return 2
    for attempt in range(2):
        try:
            urllib.request.urlopen(base + PATHS[command], timeout=30).read()
            return 0
        except OSError:
            if attempt or command != "show":
                break
            start_hub()                         # nothing answered: run the hub without OBS, then ask again
            time.sleep(3)
    if command.startswith("x-"):
        os.startfile("https://studio.x.com/live")     # no hub: at least show X's page
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
