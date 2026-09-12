"""Small local credential store backed by Windows DPAPI."""

import base64
import ctypes
import json
import os
import tempfile
from ctypes import wintypes


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _protect(value):
    raw = str(value or "").encode("utf-8")
    if not raw:
        return ""
    if os.name != "nt":
        return "plain:" + base64.b64encode(raw).decode("ascii")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    source = _DataBlob(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char)))
    target = _DataBlob()
    if not crypt32.CryptProtectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)):
        raise OSError("Windows DPAPI não protegeu a credencial.")
    try:
        protected = ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel32.LocalFree(target.pbData)
    return "dpapi:" + base64.b64encode(protected).decode("ascii")


def _unprotect(value):
    encoded = str(value or "")
    if not encoded:
        return ""
    prefix, _, payload = encoded.partition(":")
    try:
        raw = base64.b64decode(payload, validate=True)
    except (ValueError, TypeError):
        return ""
    if prefix == "plain":
        return raw.decode("utf-8")
    if prefix != "dpapi" or os.name != "nt":
        return ""
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    source = _DataBlob(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char)))
    target = _DataBlob()
    if not crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)):
        return ""
    try:
        return ctypes.string_at(target.pbData, target.cbData).decode("utf-8")
    finally:
        kernel32.LocalFree(target.pbData)


class CredentialStore:
    def __init__(self, path):
        self.path = os.path.abspath(path)

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            stored = payload.get("credentials") if isinstance(payload, dict) else {}
            if not isinstance(stored, dict):
                return {}
            result = {}
            for platform, values in stored.items():
                if not isinstance(values, dict):
                    continue
                result[str(platform)] = {
                    str(key): _unprotect(value)
                    for key, value in values.items()
                    if isinstance(value, str)
                }
            return result
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def save(self, credentials):
        stored = {
            str(platform): {
                str(key): _protect(value)
                for key, value in (values or {}).items()
                if str(value or "")
            }
            for platform, values in (credentials or {}).items()
        }
        directory = os.path.dirname(self.path)
        os.makedirs(directory, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="credentials-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"version": 1, "credentials": stored}, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
