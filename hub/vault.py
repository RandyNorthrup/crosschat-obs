"""Secrets at rest (sign-in tokens, the Rumble API URL): bytes only this user on this computer can read back.

Windows: DPAPI, for the current Windows user. macOS: AES-256 (CommonCrypto) sealed with HMAC-SHA256, under a random key
CrossChat keeps in the login Keychain (Security framework), so a copied file is useless on another account or Mac.
Linux: the same AES-256 and HMAC-SHA256 (OpenSSL's libcrypto, which Python itself uses), under a random key CrossChat
keeps in the desktop keyring through the Secret Service API (GNOME Keyring, KWallet, KeePassXC), by libsecret's
secret-tool. With no keyring to keep the key in, nothing is saved at all (Unavailable): never a plain-text fallback.
Either way the file is just bytes to the rest of CrossChat: protect() to write it, unprotect() to read it.
"""
import base64
import ctypes
import hashlib
import hmac
import os
import subprocess
import sys

SERVICE = "CrossChat"                        # the Keychain item: service "CrossChat", account "file key" (macOS)
ACCOUNT = "file key"                         # (on Linux, the keyring item's attributes: service and account)


class Unavailable(OSError):
    """There is nowhere safe to keep CrossChat's key (Linux without a desktop keyring): the secret is not saved."""


def refusal(error):
    """What to tell the streamer when protect() failed: the keyring's own story, else that encrypting failed."""
    if isinstance(error, Unavailable):
        return str(error)
    return "CrossChat couldn't encrypt the sign-in on this computer (%s), so it didn't keep it." % error


# ---- Linux: the desktop keyring, through libsecret's secret-tool --------------------------------------------------
# (Defined on every system so the tests check them anywhere; only Linux uses them.) The key goes to secret-tool on its
# standard input and comes back on its standard output, never on a command line, where other users could see it.
SECRET_TOOL = "secret-tool"
KEYRING_TIMEOUT = 120                        # time to answer the keyring's unlock prompt, if it shows one
LABEL = "CrossChat: key for saved sign-ins"  # what the keyring's own window (Passwords and Keys, KWallet) shows
NO_KEYRING = ("CrossChat keeps sign-ins encrypted under a key in your desktop keyring (GNOME Keyring, KWallet or another "
              "Secret Service), and couldn't reach one%s. Nothing was saved. Install your desktop's keyring and secret-tool "
              "(libsecret-tools on Ubuntu and Debian, libsecret on Fedora and Arch), sign in to the desktop, then try again.")


def _secret_tool(args, secret=None, run=subprocess.run):
    """(stdout, stderr) of secret-tool with `args` (attributes only). `secret`, when given, goes on its stdin."""
    feed = {"input": secret} if secret is not None else {"stdin": subprocess.DEVNULL}
    try:
        done = run([SECRET_TOOL, *args], capture_output=True, timeout=KEYRING_TIMEOUT, **feed)
    except FileNotFoundError:
        raise Unavailable(NO_KEYRING % " (secret-tool isn't installed)") from None
    except subprocess.TimeoutExpired:
        raise Unavailable(NO_KEYRING % " (it didn't answer in time: is it locked?)") from None
    except (OSError, subprocess.SubprocessError) as error:
        raise Unavailable(NO_KEYRING % (" (%s)" % error.__class__.__name__)) from None
    return done.stdout or b"", done.stderr or b""


def _said(stderr):
    """secret-tool's complaint, short, for the message (it names D-Bus problems, never a secret)."""
    text = stderr.decode("utf-8", "replace").strip().splitlines()
    return (" (%s)" % text[-1][:160]) if text else ""


def _attributes():
    return ["service", SERVICE, "account", ACCOUNT]


def _keyring_read(run=subprocess.run):
    """The 64-byte key from the keyring, or None when there is none. Unavailable when no keyring answered.

    secret-tool's exit code can't be trusted here (some versions end with 0 even when D-Bus is unreachable), so what
    it printed decides."""
    out, err = _secret_tool(["lookup", *_attributes()], run=run)
    text = out.strip()
    if not text:
        if err.strip():
            raise Unavailable(NO_KEYRING % _said(err))
        return None
    try:
        key = base64.b64decode(text, validate=True)
    except ValueError:
        key = b""
    if len(key) != 64:
        raise OSError("CrossChat's key in the keyring is not usable")
    return key


def _keyring_make(run=subprocess.run):
    """Store a new random key in the keyring and read it back (also right when another CrossChat stored one at the
    same moment: whichever the keyring kept is the key). Unavailable when it isn't there afterwards."""
    _, err = _secret_tool(["store", "--label=" + LABEL, *_attributes()], secret=base64.b64encode(os.urandom(64)), run=run)
    key = _keyring_read(run)
    if key is None:
        raise Unavailable(NO_KEYRING % _said(err))
    return key


def _keyring_forget(run=subprocess.run):
    """Remove the key from the keyring. True when it's gone (or was never there), False when no keyring answered."""
    try:
        _secret_tool(["clear", *_attributes()], run=run)
        return _keyring_read(run) is None
    except OSError:
        return False


if sys.platform == "win32":
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_char))]

    def _blob(data):
        buffer = ctypes.create_string_buffer(data, len(data))
        return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer

    def protect(data):
        """Encrypt bytes for the current Windows user (DPAPI)."""
        blob, keep = _blob(data)
        out = _Blob()
        if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(blob), None, None, None, None, 0x1, ctypes.byref(out)):
            raise OSError("CryptProtectData failed")
        try:
            return ctypes.string_at(out.data, out.size)
        finally:
            ctypes.windll.kernel32.LocalFree(out.data)
            del keep

    def unprotect(data):
        blob, keep = _blob(data)
        out = _Blob()
        if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(blob), None, None, None, None, 0x1, ctypes.byref(out)):
            raise OSError("CryptUnprotectData failed")
        try:
            return ctypes.string_at(out.data, out.size)
        finally:
            ctypes.windll.kernel32.LocalFree(out.data)
            del keep

    def forget_key():
        """Nothing to remove on Windows: DPAPI's keys belong to the Windows account."""
        return True

elif sys.platform == "darwin":
    _cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    _sec = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
    _system = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    _ref = ctypes.c_void_p
    _cf.CFDataCreate.restype, _cf.CFDataCreate.argtypes = _ref, [_ref, ctypes.c_char_p, ctypes.c_long]
    _cf.CFDataGetLength.restype, _cf.CFDataGetLength.argtypes = ctypes.c_long, [_ref]
    _cf.CFDataGetBytePtr.restype, _cf.CFDataGetBytePtr.argtypes = ctypes.c_void_p, [_ref]
    _cf.CFStringCreateWithCString.restype, _cf.CFStringCreateWithCString.argtypes = _ref, [_ref, ctypes.c_char_p, ctypes.c_uint32]
    _cf.CFDictionaryCreate.restype = _ref
    _cf.CFDictionaryCreate.argtypes = [_ref, ctypes.POINTER(_ref), ctypes.POINTER(_ref), ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]
    _cf.CFRelease.restype, _cf.CFRelease.argtypes = None, [_ref]
    for _name in ("SecItemAdd", "SecItemCopyMatching"):
        getattr(_sec, _name).restype, getattr(_sec, _name).argtypes = ctypes.c_int32, [_ref, ctypes.POINTER(_ref)]
    _sec.SecItemDelete.restype, _sec.SecItemDelete.argtypes = ctypes.c_int32, [_ref]
    _system.CCCrypt.restype = ctypes.c_int32
    _system.CCCrypt.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p,
                                ctypes.c_char_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    _NOT_FOUND, _DUPLICATE = -25300, -25299   # errSecItemNotFound, errSecDuplicateItem
    _MAGIC = b"CCK1"                        # this file format: magic, IV (16), AES-256-CBC ciphertext, HMAC-SHA256 (32)

    def _constant(library, name):
        return _ref.in_dll(library, name)

    def _text(value):
        return _cf.CFStringCreateWithCString(None, value.encode(), 0x08000100)       # kCFStringEncodingUTF8

    def _query(**extra):
        """A Keychain query for CrossChat's key, as a CFDictionary (the caller releases it and every value in `owned`)."""
        owned = [_text(SERVICE), _text(ACCOUNT)]
        pairs = [("kSecClass", _constant(_sec, "kSecClassGenericPassword")), ("kSecAttrService", owned[0]), ("kSecAttrAccount", owned[1])]
        for key, value in extra.items():
            if isinstance(value, bytes):
                value = _cf.CFDataCreate(None, value, len(value))
                owned.append(value)
            pairs.append((key, value))
        keys = (_ref * len(pairs))(*[_constant(_sec, k).value for k, _ in pairs])
        values = (_ref * len(pairs))(*[v.value if isinstance(v, _ref) else v for _, v in pairs])
        made = _cf.CFDictionaryCreate(None, keys, values, len(pairs), ctypes.addressof(ctypes.c_char.in_dll(_cf, "kCFTypeDictionaryKeyCallBacks")),
                                      ctypes.addressof(ctypes.c_char.in_dll(_cf, "kCFTypeDictionaryValueCallBacks")))
        return made, owned

    def _release(made, owned):
        for item in [made, *owned]:
            if item:
                _cf.CFRelease(item)

    def _read_key():
        query, owned = _query(kSecReturnData=_constant(_cf, "kCFBooleanTrue"), kSecMatchLimit=_constant(_sec, "kSecMatchLimitOne"))
        found = _ref()
        try:
            status = _sec.SecItemCopyMatching(query, ctypes.byref(found))
        finally:
            _release(query, owned)
        if status == _NOT_FOUND:
            return None
        if status != 0 or not found.value:
            raise OSError("The Keychain refused CrossChat's key (error %d)" % status)
        try:
            return ctypes.string_at(_cf.CFDataGetBytePtr(found), _cf.CFDataGetLength(found))
        finally:
            _cf.CFRelease(found)

    def _key():
        """CrossChat's 64-byte file key (32 to encrypt, 32 to seal), made and stored in the Keychain the first time."""
        key = _read_key()
        if key is None:
            query, owned = _query(kSecValueData=os.urandom(64))
            try:
                status = _sec.SecItemAdd(query, None)
            finally:
                _release(query, owned)
            if status not in (0, _DUPLICATE):
                raise OSError("The Keychain refused to store CrossChat's key (error %d)" % status)
            key = _read_key()                   # also right when another CrossChat made it at the same moment
        if not key or len(key) != 64:
            raise OSError("CrossChat's key in the Keychain is not usable")
        return key

    def _aes(operation, key, iv, data):
        out = ctypes.create_string_buffer(len(data) + 16)
        moved = ctypes.c_size_t()
        status = _system.CCCrypt(operation, 0, 1, key, len(key), iv, data, len(data), out, len(out), ctypes.byref(moved))  # AES, PKCS7
        if status != 0:
            raise OSError("CCCrypt failed (%d)" % status)
        return out.raw[:moved.value]

    def protect(data):
        """Encrypt bytes under CrossChat's key in this user's login Keychain (macOS)."""
        key = _key()
        iv = os.urandom(16)
        body = _MAGIC + iv + _aes(0, key[:32], iv, data)
        return body + hmac.new(key[32:], body, hashlib.sha256).digest()

    def unprotect(data):
        if len(data) < len(_MAGIC) + 16 + 16 + 32 or not data.startswith(_MAGIC):
            raise OSError("not a CrossChat secret")
        key = _key()
        body, seal = data[:-32], data[-32:]
        if not hmac.compare_digest(hmac.new(key[32:], body, hashlib.sha256).digest(), seal):
            raise OSError("this secret was changed, or made for another account or Mac")
        return _aes(1, key[:32], body[len(_MAGIC):len(_MAGIC) + 16], body[len(_MAGIC) + 16:])

    def forget_key():
        """Remove CrossChat's key from the Keychain (the uninstaller does this; every saved secret becomes unreadable)."""
        query, owned = _query()
        try:
            status = _sec.SecItemDelete(query)
        finally:
            _release(query, owned)
        return status in (0, _NOT_FOUND)

elif sys.platform.startswith("linux"):
    import contextlib
    import fcntl
    import time

    _MAGIC = b"CCK1"                        # the Mac's file format: magic, IV (16), AES-256-CBC ciphertext, HMAC-SHA256 (32)
    _crypto = None

    def _libcrypto():
        """OpenSSL's libcrypto, the one Python's own ssl and hashlib use (3.x, or 1.1 on older systems)."""
        global _crypto
        if _crypto is None:
            import ctypes.util

            def found():
                yield from ("libcrypto.so.3", "libcrypto.so.1.1")
                yield ctypes.util.find_library("crypto")      # (asks ldconfig: only when the usual names aren't there)

            for name in found():
                try:
                    lib = ctypes.CDLL(name) if name else None
                except OSError:
                    continue
                if lib is None:
                    continue
                lib.EVP_CIPHER_CTX_new.restype, lib.EVP_CIPHER_CTX_new.argtypes = ctypes.c_void_p, []
                lib.EVP_CIPHER_CTX_free.restype, lib.EVP_CIPHER_CTX_free.argtypes = None, [ctypes.c_void_p]
                lib.EVP_aes_256_cbc.restype, lib.EVP_aes_256_cbc.argtypes = ctypes.c_void_p, []
                lib.EVP_CipherInit_ex.restype = ctypes.c_int
                lib.EVP_CipherInit_ex.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
                for step in ("EVP_CipherUpdate", "EVP_CipherFinal_ex"):
                    getattr(lib, step).restype = ctypes.c_int
                lib.EVP_CipherUpdate.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.c_char_p, ctypes.c_int]
                lib.EVP_CipherFinal_ex.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
                _crypto = lib
                break
            else:
                raise OSError("OpenSSL's libcrypto wasn't found, so CrossChat can't encrypt here")
        return _crypto

    def _aes(encrypt, key, iv, data):
        """AES-256-CBC with PKCS#7 padding."""
        lib = _libcrypto()
        ctx = lib.EVP_CIPHER_CTX_new()
        if not ctx:
            raise OSError("OpenSSL couldn't start AES")
        try:
            out = ctypes.create_string_buffer(len(data) + 32)
            moved, last = ctypes.c_int(), ctypes.c_int()
            if (lib.EVP_CipherInit_ex(ctx, lib.EVP_aes_256_cbc(), None, key, iv, 1 if encrypt else 0) != 1
                    or lib.EVP_CipherUpdate(ctx, out, ctypes.byref(moved), data, len(data)) != 1
                    or lib.EVP_CipherFinal_ex(ctx, ctypes.byref(out, moved.value), ctypes.byref(last)) != 1):
                raise OSError("AES failed")
            return out.raw[:moved.value + last.value]
        finally:
            lib.EVP_CIPHER_CTX_free(ctx)

    @contextlib.contextmanager
    def _one_at_a_time():
        """Two CrossChats making the first key at the same moment must not each keep their own: they take turns (a lock
        file in this user's own runtime folder, which nobody else can write to)."""
        folder = os.environ.get("XDG_RUNTIME_DIR") or ""
        if not os.path.isdir(folder):
            yield
            return
        with open(os.path.join(folder, "crosschat-key.lock"), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    _known = {}                             # SERVICE -> its key, once read or made: later uses don't ask the keyring again
    _refused = {"until": 0.0, "why": ""}    # the keyring said no, or its unlock prompt went unanswered: a minute's rest,
    BACK_OFF = 60                           # so the hub's start doesn't ask four times over

    def _read_key():
        return _keyring_read()

    def _key(make=True):
        """CrossChat's 64-byte file key (32 to encrypt, 32 to seal), made and stored in the keyring the first time
        (`make`); None when there is none and `make` is off."""
        if SERVICE in _known:
            return _known[SERVICE]
        if time.time() < _refused["until"]:
            raise Unavailable(_refused["why"])
        try:
            with _one_at_a_time():
                key = _keyring_read()
                if key is None and make:
                    key = _keyring_make()
        except Unavailable as error:
            _refused.update(until=time.time() + BACK_OFF, why=str(error))
            raise
        if key is not None:
            _known[SERVICE] = key
        return key

    def protect(data):
        """Encrypt bytes under CrossChat's key in this user's desktop keyring (Linux). Unavailable without a keyring."""
        key = _key()
        iv = os.urandom(16)
        body = _MAGIC + iv + _aes(True, key[:32], iv, data)
        return body + hmac.new(key[32:], body, hashlib.sha256).digest()

    def unprotect(data):
        if len(data) < len(_MAGIC) + 16 + 16 + 32 or not data.startswith(_MAGIC):
            raise OSError("not a CrossChat secret")
        key = _key(make=False)              # (no key: nothing it sealed can be opened, so none is made here)
        if key is None:
            raise OSError("CrossChat's key isn't in the keyring (it was removed, or this is another account or computer)")
        body, seal = data[:-32], data[-32:]
        if not hmac.compare_digest(hmac.new(key[32:], body, hashlib.sha256).digest(), seal):
            raise OSError("this secret was changed, or made for another account or computer")
        return _aes(False, key[:32], body[len(_MAGIC):len(_MAGIC) + 16], body[len(_MAGIC) + 16:])

    def forget_key():
        """Remove CrossChat's key from the keyring (the uninstaller does this; every saved secret becomes unreadable)."""
        _known.pop(SERVICE, None)
        _refused.update(until=0.0, why="")
        return _keyring_forget()

else:
    def protect(data):
        raise Unavailable("CrossChat keeps secrets only on Windows, macOS and Linux")

    def unprotect(data):
        raise OSError("CrossChat keeps secrets only on Windows, macOS and Linux")

    def forget_key():
        return True
