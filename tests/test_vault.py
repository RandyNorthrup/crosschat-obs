"""Secrets at rest: readable back on this account, useless anywhere else, and never stored as plain text."""
import base64
import json
import subprocess
import sys

import discord_relay
import hub
import kick_api
import pytest
import rumble_api
import twitch_api
import vault
from test_companion import post, run, serving

SECRET = b'{"tokens": {"access_token": "AT-123", "refresh_token": "RT-456"}}'
linux_only = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the desktop keyring is a Linux matter")


@pytest.mark.keyring
def test_a_secret_comes_back_and_is_never_stored_plain():
    sealed = vault.protect(SECRET)
    assert b"AT-123" not in sealed and vault.unprotect(sealed) == SECRET
    assert vault.protect(SECRET) != sealed                    # fresh randomness every time
    assert vault.unprotect(vault.protect(b"")) == b""


@pytest.mark.keyring
def test_a_changed_secret_is_refused():
    sealed = bytearray(vault.protect(SECRET))
    sealed[len(sealed) // 2] ^= 1
    with pytest.raises(OSError):
        vault.unprotect(bytes(sealed))
    with pytest.raises(OSError):
        vault.unprotect(b"not a secret at all")


@pytest.mark.skipif(sys.platform != "darwin", reason="the Keychain is a Mac matter")
def test_on_a_mac_the_key_lives_in_the_keychain_and_forgetting_it_locks_every_secret():
    sealed = vault.protect(SECRET)
    assert sealed.startswith(b"CCK1") and len(vault._read_key()) == 64
    assert vault.forget_key() and vault._read_key() is None
    with pytest.raises(OSError):                               # a new key can't open what the old one sealed
        vault.unprotect(sealed)
    assert vault.forget_key()                                  # removing what isn't there is fine


@linux_only
@pytest.mark.keyring
def test_on_linux_the_key_lives_in_the_keyring_and_forgetting_it_locks_every_secret():
    sealed = vault.protect(SECRET)
    assert sealed.startswith(b"CCK1") and len(vault._read_key()) == 64
    found = subprocess.run(["secret-tool", "search", "--all", "service", vault.SERVICE], capture_output=True, text=True)
    assert "label = " + vault.LABEL in found.stdout             # one item, named so the keyring's own window says what it is
    assert vault.forget_key() and vault._read_key() is None
    with pytest.raises(OSError):                               # without the key, nothing it sealed opens (and none is made)
        vault.unprotect(sealed)
    assert vault._read_key() is None
    assert vault.forget_key()                                  # removing what isn't there is fine


@linux_only
def test_on_linux_aes_is_the_real_thing():
    """AES-256-CBC from OpenSSL's libcrypto, checked against NIST SP 800-38A (F.2.5, the first block)."""
    key = bytes.fromhex("603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4")
    plain = bytes.fromhex("6bc1bee22e409f96e93d7e117393172a")
    sealed = vault._aes(True, key, bytes(range(16)), plain)
    assert sealed[:16].hex() == "f58c4c04d6e5f1ba779eabfb5f7bfbd6" and len(sealed) == 32      # + a block of padding
    assert vault._aes(False, key, bytes(range(16)), sealed) == plain


# ---- the keyring through secret-tool, with a stand-in for it (these run on every system) ---------------------------
class Keyring:
    """A stand-in for secret-tool and the Secret Service behind it. `broken` is what secret-tool says when no keyring
    answers (it can still end with 0, so CrossChat must not trust that)."""

    def __init__(self, broken="", missing=False):
        self.items, self.calls, self.broken, self.missing = {}, [], broken, missing

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        if self.missing:
            raise FileNotFoundError(argv[0])
        assert kw.get("capture_output") and kw.get("timeout")
        if self.broken:
            return subprocess.CompletedProcess(argv, 0, b"", ("secret-tool: " + self.broken + "\n").encode())
        verb, rest = argv[1], [a for a in argv[2:] if not a.startswith("--")]
        where = tuple(rest)
        if verb == "store":
            self.items[where] = kw["input"]
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        if verb == "lookup":
            found = self.items.get(where)
            return subprocess.CompletedProcess(argv, 0 if found else 1, found or b"", b"")
        if verb == "clear":
            return subprocess.CompletedProcess(argv, 0 if self.items.pop(where, None) else 1, b"", b"")
        raise AssertionError(argv)


def test_the_key_goes_to_secret_tool_on_stdin_never_on_its_command_line():
    keyring = Keyring()
    key = vault._keyring_make(run=keyring)
    assert len(key) == 64 and vault._keyring_read(run=keyring) == key
    store = [c for c in keyring.calls if c[0][1] == "store"][0]
    assert store[0][0] == "secret-tool" and store[1]["input"] == base64.b64encode(key)
    assert store[0][2:] == ["--label=" + vault.LABEL, "service", vault.SERVICE, "account", vault.ACCOUNT]
    encoded = base64.b64encode(key).decode()
    for argv, kw in keyring.calls:                             # nobody else's `ps` can see it
        assert not any(encoded in a for a in argv)
        assert "input" in kw or kw.get("stdin") == subprocess.DEVNULL
    assert vault._keyring_forget(run=keyring) and vault._keyring_read(run=keyring) is None
    assert vault._keyring_forget(run=keyring)                  # nothing there: fine too


def test_without_a_keyring_nothing_is_saved_and_the_streamer_is_told_why():
    broken = Keyring(broken="Cannot autolaunch D-Bus without X11 $DISPLAY")
    with pytest.raises(vault.Unavailable) as error:
        vault._keyring_make(run=broken)
    said = str(error.value)
    assert "desktop keyring" in said and "Nothing was saved" in said and "Cannot autolaunch D-Bus" in said
    assert vault.refusal(error.value) == said
    with pytest.raises(vault.Unavailable):
        vault._keyring_read(run=broken)
    assert vault._keyring_forget(run=broken) is False
    with pytest.raises(vault.Unavailable) as error:
        vault._keyring_read(run=Keyring(missing=True))
    assert "secret-tool isn't installed" in str(error.value) and "libsecret-tools" in str(error.value)

    def hangs(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw["timeout"])

    with pytest.raises(vault.Unavailable) as error:
        vault._keyring_read(run=hangs)
    assert "didn't answer in time" in str(error.value)


def test_a_damaged_key_in_the_keyring_is_not_used():
    keyring = Keyring()
    keyring.items[("service", vault.SERVICE, "account", vault.ACCOUNT)] = b"not base64 at all!"
    with pytest.raises(OSError) as error:
        vault._keyring_read(run=keyring)
    assert not isinstance(error.value, vault.Unavailable)
    keyring.items[("service", vault.SERVICE, "account", vault.ACCOUNT)] = base64.b64encode(b"short")
    with pytest.raises(OSError):
        vault._keyring_read(run=keyring)


# ---- sign-ins that can't be encrypted are not kept at all -----------------------------------------------------------
def no_keyring(data):
    raise vault.Unavailable(vault.NO_KEYRING % "")


def test_a_twitch_or_kick_sign_in_that_cant_be_encrypted_is_not_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(twitch_api, "protect", no_keyring)
    t = twitch_api.Twitch("client", str(tmp_path / "twitch.bin"))
    t.tokens, t.user = {"access_token": "tok", "refresh_token": "ref"}, {"id": "1", "login": "me"}
    with pytest.raises(twitch_api.TwitchError) as error:
        t.save()
    assert "desktop keyring" in str(error.value) and not (tmp_path / "twitch.bin").exists()
    assert t.tokens == {} and not t.on() and t.state() == {"state": "error", "why": str(error.value)}

    monkeypatch.setattr(kick_api, "protect", no_keyring)
    k = kick_api.Kick("id", "secret", str(tmp_path / "kick.bin"), "http://localhost:4466/kick/callback")
    k.tokens, k.user = {"access_token": "tok"}, {"id": 1, "login": "me"}
    with pytest.raises(kick_api.KickError):
        k.save()
    assert k.tokens == {} and not k.on() and not (tmp_path / "kick.bin").exists() and "desktop keyring" in k.state()["why"]


def test_when_encrypting_fails_for_another_reason_the_message_says_so():
    assert "couldn't encrypt" in vault.refusal(OSError("CryptProtectData failed"))


def test_a_discord_webhook_that_cant_be_encrypted_is_not_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(discord_relay, "protect", no_keyring)
    d = discord_relay.Discord(str(tmp_path / "discord.bin"), hub.NAMES)
    hook = "https://discord.com/api/webhooks/123456789012345678/" + "t" * 68
    monkeypatch.setattr(d, "ask", lambda url: {"id": "123456789012345678", "name": "stream-chat"})
    with pytest.raises(vault.Unavailable):
        d.set(hook)
    assert not d.on() and d.url == "" and not (tmp_path / "discord.bin").exists()


def test_the_hub_says_why_when_rumble_cant_be_kept(home, monkeypatch):
    home({})
    monkeypatch.setattr(rumble_api, "protect", no_keyring)

    async def test(port):
        answer = json.loads((await post(port, "/rumble/connect", {"url": "https://rumble.com/-livestream-api/get-data?key=ABCDEFGH12"}))[2])
        assert answer["ok"] is False and "desktop keyring" in answer["why"] and not hub.RB.on()
    run(serving(test))
