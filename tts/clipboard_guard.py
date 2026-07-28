"""Full-fidelity clipboard snapshot/restore for the Ctrl+C selection fallback.

pyperclip can only preserve plain text, so the fallback used to refuse whenever
the clipboard held anything else (a screenshot, copied files) — which read as
"this window isn't usable". This module backs up the standard HGLOBAL-backed
formats directly via Win32 so those payloads can be restored byte-for-byte:

    CF_UNICODETEXT (13)  text
    CF_DIB (8) / CF_DIBV5 (17)  images/screenshots
    CF_HDROP (15)  copied files

Private/delayed-render app formats can't be safely duplicated; a snapshot
records how many of those it had to skip so the caller can decide. Contents are
held only in memory for the duration of one capture and never logged.
"""
from __future__ import annotations

import ctypes
import time

CF_UNICODETEXT = 13
CF_DIB = 8
CF_DIBV5 = 17
CF_HDROP = 15
SAFE_FORMATS = (CF_UNICODETEXT, CF_DIB, CF_DIBV5, CF_HDROP)
GMEM_MOVEABLE = 0x0002


class ClipboardSnapshot:
    __slots__ = ("formats", "skipped")

    def __init__(self, formats, skipped):
        self.formats = formats      # {int format id: bytes}
        self.skipped = skipped      # count of formats we could not back up


def _user32():
    u = ctypes.windll.user32
    k = ctypes.windll.kernel32
    k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalLock.argtypes = [ctypes.c_void_p]
    k.GlobalUnlock.argtypes = [ctypes.c_void_p]
    k.GlobalSize.restype = ctypes.c_size_t
    k.GlobalSize.argtypes = [ctypes.c_void_p]
    k.GlobalAlloc.restype = ctypes.c_void_p
    u.GetClipboardData.restype = ctypes.c_void_p
    u.SetClipboardData.restype = ctypes.c_void_p
    u.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    return u, k


def _open_clipboard(u, retries=10, delay=0.02):
    """The clipboard is a shared resource; another app may hold it briefly."""
    for _ in range(retries):
        if u.OpenClipboard(None):
            return True
        time.sleep(delay)
    return False


def snapshot():
    """Copy every SAFE format off the clipboard. Returns a ClipboardSnapshot,
    or None if the clipboard could not be opened. Never raises."""
    try:
        u, k = _user32()
        if not _open_clipboard(u):
            return None
        try:
            formats, skipped = {}, 0
            fmt = 0
            while True:
                fmt = u.EnumClipboardFormats(fmt)
                if not fmt:
                    break
                if fmt not in SAFE_FORMATS:
                    skipped += 1
                    continue
                handle = u.GetClipboardData(fmt)
                if not handle:
                    skipped += 1
                    continue
                ptr = k.GlobalLock(handle)
                if not ptr:
                    skipped += 1
                    continue
                try:
                    size = k.GlobalSize(handle)
                    formats[fmt] = ctypes.string_at(ptr, size)
                finally:
                    k.GlobalUnlock(handle)
            return ClipboardSnapshot(formats, skipped)
        finally:
            u.CloseClipboard()
    except Exception:
        return None


def restore(snap) -> bool:
    """Put a snapshot's formats back on the clipboard. Returns success.
    Never raises."""
    if snap is None:
        return False
    try:
        u, k = _user32()
        if not _open_clipboard(u):
            return False
        try:
            u.EmptyClipboard()
            for fmt, data in snap.formats.items():
                handle = k.GlobalAlloc(GMEM_MOVEABLE, len(data) or 1)
                if not handle:
                    continue
                ptr = k.GlobalLock(handle)
                if not ptr:
                    continue
                try:
                    ctypes.memmove(ptr, data, len(data))
                finally:
                    k.GlobalUnlock(handle)
                # On success the system owns the handle; do not free it.
                u.SetClipboardData(fmt, handle)
            return True
        finally:
            u.CloseClipboard()
    except Exception:
        return False
