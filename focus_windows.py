"""Windows active-window queries (extracted from app.py, behavior unchanged)."""
import ctypes


class WindowsFocus:
    def current_id(self):
        import ctypes.wintypes as wintypes
        u32 = ctypes.windll.user32
        u32.GetForegroundWindow.restype = wintypes.HWND
        return int(u32.GetForegroundWindow() or 0)

    def active_process(self):
        """Lowercased exe basename of the focused window, or '' on failure."""
        try:
            import os as _os
            import ctypes.wintypes as wintypes
            u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
            # explicit signatures: default ctypes int types truncate 64-bit
            # handles/pointers on Win64
            u32.GetForegroundWindow.restype = wintypes.HWND
            u32.GetWindowThreadProcessId.argtypes = [
                wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            k32.OpenProcess.restype = wintypes.HANDLE
            k32.OpenProcess.argtypes = [
                wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            k32.QueryFullProcessImageNameW.argtypes = [
                wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                ctypes.POINTER(wintypes.DWORD)]
            k32.CloseHandle.argtypes = [wintypes.HANDLE]
            hwnd = u32.GetForegroundWindow()
            pid = wintypes.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            h = k32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFO
            if not h:
                return ""
            try:
                buf = ctypes.create_unicode_buffer(260)
                size = wintypes.DWORD(260)
                k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
                return _os.path.basename(buf.value).lower()
            finally:
                k32.CloseHandle(h)
        except Exception:
            return ""

    def active_title(self):
        """Window title of the focused window, or '' on failure."""
        try:
            import ctypes.wintypes as wintypes
            u32 = ctypes.windll.user32
            u32.GetForegroundWindow.restype = wintypes.HWND
            u32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            u32.GetWindowTextLengthW.restype = ctypes.c_int
            u32.GetWindowTextW.argtypes = [
                wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            u32.GetWindowTextW.restype = ctypes.c_int
            hwnd = u32.GetForegroundWindow()
            if not hwnd:
                return ""
            length = u32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return ""
            buf = ctypes.create_unicode_buffer(length + 1)
            u32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except Exception:
            return ""
