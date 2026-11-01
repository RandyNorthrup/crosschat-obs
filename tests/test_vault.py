"""Secrets at rest: readable back on this account, useless anywhere else, and never stored as plain text."""
import sys

import pytest
import vault

SECRET = b'{"tokens": {"access_token": "AT-123", "refresh_token": "RT-456"}}'


def test_a_secret_comes_back_and_is_never_stored_plain():
    sealed = vault.protect(SECRET)
    assert b"AT-123" not in sealed and vault.unprotect(sealed) == SECRET
    assert vault.protect(SECRET) != sealed                    # fresh randomness every time
    assert vault.unprotect(vault.protect(b"")) == b""


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
