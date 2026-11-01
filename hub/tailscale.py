"""This PC's own Tailscale address, for the companion away from home.

Tailscale (tailscale.com) joins the streamer's own devices in a private, encrypted network. With "remote":
{"tailscale": true} the companion also listens on the PC's Tailscale address, so a phone with Tailscale on reaches it
from anywhere, pairing still required.

An address in 100.64.0.0/10 proves nothing on its own: internet providers hand out that range too (carrier-grade NAT),
and listening there could put the companion on the provider's network. So the address only counts when Windows has it
on Tailscale's own network adapter, and that adapter is up. On Linux the same rule: the address of Tailscale's own
network interface (tailscale0, or another name starting with "tailscale"), only while it is up.
"""
import ipaddress
import re
import socket
import struct
import subprocess
import sys

NO_WINDOW = 0x08000000
SIOCGIFFLAGS, SIOCGIFADDR = 0x8913, 0x8915             # Linux: an interface's flags, its IPv4 address
IFF_UP, IFF_RUNNING = 0x1, 0x40
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


def linux_interfaces():
    """(name, IPv4 address, flags) of this computer's network interfaces named tailscale*, asked of the kernel
    directly (no program is run). Linux only."""
    import fcntl
    found = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        for _, name in socket.if_nameindex():
            if not name.startswith("tailscale"):
                continue
            request = struct.pack("256s", name.encode()[:15])
            try:
                flags = struct.unpack("H", fcntl.ioctl(s.fileno(), SIOCGIFFLAGS, request)[16:18])[0]
                ip = socket.inet_ntoa(fcntl.ioctl(s.fileno(), SIOCGIFADDR, request)[20:24])
            except OSError:                      # no IPv4 address on it (yet)
                continue
            found.append((name, ip, flags))
    return found


def linux_address(interfaces=None):
    """The Tailscale address on an interface of Tailscale's that is up and running, or ''."""
    try:
        listed = linux_interfaces() if interfaces is None else interfaces
    except OSError:
        return ""
    return pick(ip for _, ip, flags in listed if flags & IFF_UP and flags & IFF_RUNNING)


def address(run=subprocess.run):
    """This PC's Tailscale address, or '' when Tailscale isn't installed, isn't running or isn't signed in. Blocking:
    the hub runs it in a worker thread."""
    if sys.platform.startswith("linux"):
        return linux_address()
    if sys.platform != "win32":                  # (not on a Mac yet: the companion there uses "remote.bind")
        return ""
    try:
        out = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ASK], capture_output=True, text=True, timeout=15,
                  creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return ""
    return pick(out.stdout.splitlines()) if out.returncode == 0 and out.stdout else ""
