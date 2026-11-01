"""This PC's own Tailscale address, for the companion away from home.

Tailscale (tailscale.com) joins the streamer's own devices in a private, encrypted network. With "remote":
{"tailscale": true} the companion also listens on the PC's Tailscale address, so a phone with Tailscale on reaches it
from anywhere, pairing still required.

An address in 100.64.0.0/10 proves nothing on its own: internet providers hand out that range too (carrier-grade NAT),
and listening there could put the companion on the provider's network. So the address only counts when Windows has it
on Tailscale's own network adapter, and that adapter is up.
"""
import ipaddress
import re
import subprocess
import sys

NO_WINDOW = 0x08000000
RANGE = ipaddress.ip_network("100.64.0.0/10")          # where Tailscale's addresses are
# The IPv4 addresses of network adapters that are up and are Tailscale's (by the driver's description, which stays
# "Tailscale Tunnel" even when the adapter is renamed, or by the adapter's name).
ASK = ("Get-NetAdapter -ErrorAction Stop | Where-Object { $_.Status -eq 'Up' -and ($_.InterfaceDescription -like 'Tailscale*' -or "
       "$_.Name -like 'Tailscale*') } | Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | ForEach-Object { $_.IPAddress }")


def pick(lines):
    """The first Tailscale address among the lines Windows answered, or ''."""
    for line in lines:
        text = line.strip()
        if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", text):
            continue
        try:
            if ipaddress.ip_address(text) in RANGE:
                return text
        except ValueError:
            continue
    return ""


def address(run=subprocess.run):
    """This PC's Tailscale address, or '' when Tailscale isn't installed, isn't running or isn't signed in. Blocking:
    the hub runs it in a worker thread."""
    if sys.platform != "win32":                  # (not on a Mac yet: the companion there uses "remote.bind")
        return ""
    try:
        out = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ASK], capture_output=True, text=True, timeout=15,
                  creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return ""
    return pick(out.stdout.splitlines()) if out.returncode == 0 and out.stdout else ""
