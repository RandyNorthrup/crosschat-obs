"""Secrets at rest (sign-in tokens, the Rumble API URL): bytes only this user on this computer can read back.

Windows: DPAPI, for the current Windows user. macOS: AES-256 (CommonCrypto) sealed with HMAC-SHA256, under a random key
CrossChat keeps in the login Keychain (Security framework), so a copied file is useless on another account or Mac.
Either way the file is just bytes to the rest of CrossChat: protect() to write it, unprotect() to read it.
"""
import ctypes
import hashlib
import hmac
import os
import sys

SERVICE = "CrossChat"                        # the Keychain item: service "CrossChat", account "file key" (macOS)
ACCOUNT = "file key"

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

else:
    def protect(data):
        raise OSError("CrossChat keeps secrets only on Windows and macOS")

    def unprotect(data):
        raise OSError("CrossChat keeps secrets only on Windows and macOS")

    def forget_key():
        return True
