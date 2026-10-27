"""การอ่านและบันทึกรหัสลำโพงใน Windows Credential Manager."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


CREDENTIAL_TARGET = "labboy-coworking-broadcast/speaker-admin"


class WinCredential(ctypes.Structure):
    class FileTime(ctypes.Structure):
        _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    _fields_ = [
        ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
        ("LastWritten", FileTime), ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def read_saved_speaker_password() -> str | None:
    """อ่านรหัสผ่านจาก Credential Manager ของบัญชี Windows ปัจจุบัน."""
    if os.name != "nt":
        return None
    advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    credential_ptr = ctypes.POINTER(WinCredential)()
    advapi.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                 ctypes.POINTER(ctypes.POINTER(WinCredential))]
    advapi.CredReadW.restype = wintypes.BOOL
    advapi.CredFree.argtypes = [ctypes.c_void_p]
    advapi.CredFree.restype = None
    if not advapi.CredReadW(CREDENTIAL_TARGET, 1, 0, ctypes.byref(credential_ptr)):
        error = ctypes.get_last_error()
        if error == 1168:
            return None
        raise OSError(error, "อ่านรหัสผ่านจาก Windows Credential Manager ไม่สำเร็จ")
    try:
        credential = credential_ptr.contents
        raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        return raw.decode("utf-16-le")
    finally:
        advapi.CredFree(credential_ptr)


def save_speaker_password(password: str) -> None:
    """บันทึกรหัสผ่านแบบผูกกับบัญชี Windows ปัจจุบัน."""
    if os.name != "nt":
        raise OSError("Windows Credential Manager ใช้ได้เฉพาะบน Windows")
    encoded = password.encode("utf-16-le")
    blob = ctypes.create_string_buffer(encoded)
    credential = WinCredential()
    credential.Flags = 0
    credential.Type = 1
    credential.TargetName = CREDENTIAL_TARGET
    credential.Comment = "labboy Coworking Broadcast speaker admin password"
    credential.CredentialBlobSize = len(encoded)
    credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = 2
    credential.AttributeCount = 0
    credential.Attributes = None
    credential.TargetAlias = None
    credential.UserName = "admin"
    advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    advapi.CredWriteW.argtypes = [ctypes.POINTER(WinCredential), wintypes.DWORD]
    advapi.CredWriteW.restype = wintypes.BOOL
    if not advapi.CredWriteW(ctypes.byref(credential), 0):
        error = ctypes.get_last_error()
        raise OSError(error, "บันทึกรหัสผ่านใน Windows Credential Manager ไม่สำเร็จ")
