"""Point & Speak trigger: a global Ctrl+Right-click gesture.

Windows has no system-wide "add an item to every app's text context menu"
extension point, so the honest equivalent is a low-level mouse hook that
watches for a MODIFIER'd right-click and fires ROAR's own action. Plain
right-click is untouched, and even the gesture click is never eaten — the
handler observes and ALWAYS passes the event on, so the app under the cursor
still shows its own menu.

The hook callback does no I/O and no capture work; it only checks the message,
the Ctrl key, and a debounce, then invokes `on_gesture` (which must be cheap —
app wiring hands off to a thread). Windows silently removes slow LL hooks, so
staying under a millisecond here is a correctness requirement, not a style one.

Pure decision logic (`should_trigger`) is unit-tested on any OS; the Win32
shell is verified live on Windows.
"""
import ctypes
import threading
import time

WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WH_MOUSE_LL = 14
WM_QUIT = 0x0012
VK_CONTROL = 0x11
DEBOUNCE_S = 0.3


def should_trigger(msg, ctrl_down, enabled, now, last_fire,
                   debounce_s=DEBOUNCE_S) -> bool:
    """True only for an enabled Ctrl + right-button-UP outside the debounce
    window. Button-up (not down) so we never race the app's own click
    handling, and a held drag-select still counts as one gesture."""
    if not enabled or not ctrl_down:
        return False
    if msg != WM_RBUTTONUP:
        return False
    return (now - last_fire) >= debounce_s


def should_suppress(msg, ctrl_down, enabled) -> bool:
    """True when this event belongs to OUR gesture and must not reach the app.

    Ctrl+Right-click is consumed on purpose. Letting it through opens the
    application's context menu, and an open menu takes keyboard focus — so the
    Ctrl+C the capture fallback sends lands in the MENU instead of the page,
    which is exactly why the gesture failed in browsers and PDF viewers.

    Both DOWN and UP are suppressed so the app never sees an orphaned
    button-down. PLAIN right-click (no Ctrl) is never touched.
    """
    return bool(enabled and ctrl_down
                and msg in (WM_RBUTTONDOWN, WM_RBUTTONUP))


class PointerGestureHook:
    """Owns the WH_MOUSE_LL hook on a dedicated message-pump thread.

    start()/stop() are idempotent and cheap; the caller (app.py) starts the
    hook only while the feature AND Read Aloud are both enabled. If the pump
    thread dies unexpectedly it is restarted once; a second death reports
    through `on_error` instead of going silently deaf.
    """

    def __init__(self, on_gesture, on_error=None):
        self._on_gesture = on_gesture
        self._on_error = on_error or (lambda msg: None)
        self._running = False
        self._restarted = False
        self._thread = None
        self._thread_id = None
        self._hook = None
        self._proc = None          # keep the WINFUNCTYPE alive (GC safety)
        self._last_fire = 0.0
        self._lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------
    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._restarted = False
        self._thread = threading.Thread(
            target=self._run, name="ROAR-pointer-gesture", daemon=True)
        self._thread.start()

    def stop(self):
        with self._lock:
            if not self._running:
                return
            self._running = False
        tid = self._thread_id
        if tid:
            try:
                ctypes.windll.user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
            except Exception:
                pass
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout=2)
        self._uninstall()
        self._thread = None
        self._thread_id = None

    # -- pump thread -------------------------------------------------------
    def _run(self):
        while True:
            try:
                self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
                if not self._install():
                    self._on_error("Point & Speak could not install its "
                                   "mouse hook.")
                    return
                self._pump()
            except Exception as exc:
                if self._running and not self._restarted:
                    self._restarted = True
                    self._uninstall()
                    continue    # one self-heal attempt
                if self._running:
                    self._on_error(f"Point & Speak stopped ({exc}). "
                                   "Toggle it off and on to retry.")
                return
            finally:
                self._uninstall()
            return  # pump exited normally (WM_QUIT)

    def _install(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        LRESULT = ctypes.c_ssize_t
        HOOKPROC = ctypes.WINFUNCTYPE(
            LRESULT, ctypes.c_int, ctypes.wintypes.WPARAM,
            ctypes.wintypes.LPARAM)

        def _callback(n_code, w_param, l_param):
            # No I/O and no capture here — Windows drops slow LL hooks.
            # Ctrl+Right-click is CONSUMED (returns 1) so no context menu opens
            # to steal the focus our capture needs; everything else passes on.
            try:
                if n_code >= 0 and w_param in (WM_RBUTTONDOWN, WM_RBUTTONUP):
                    ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                    if should_suppress(w_param, ctrl, self._running):
                        if w_param == WM_RBUTTONUP:
                            now = time.monotonic()
                            if should_trigger(WM_RBUTTONUP, ctrl, self._running,
                                              now, self._last_fire):
                                self._last_fire = now
                                try:
                                    self._on_gesture()
                                except Exception:
                                    pass
                        return 1   # consume: the app never sees this click
            except Exception:
                pass
            return user32.CallNextHookEx(self._hook, n_code, w_param, l_param)

        self._proc = HOOKPROC(_callback)
        # Explicit prototypes: default ctypes int returns truncate 64-bit
        # handles (same class of bug as the HWND fix in focus_windows.py).
        kernel32.GetModuleHandleW.restype = ctypes.wintypes.HMODULE
        kernel32.GetModuleHandleW.argtypes = [ctypes.wintypes.LPCWSTR]
        user32.SetWindowsHookExW.restype = ctypes.wintypes.HHOOK
        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int, HOOKPROC, ctypes.wintypes.HMODULE,
            ctypes.wintypes.DWORD]
        user32.CallNextHookEx.restype = ctypes.c_ssize_t
        user32.CallNextHookEx.argtypes = [
            ctypes.wintypes.HHOOK, ctypes.c_int, ctypes.wintypes.WPARAM,
            ctypes.wintypes.LPARAM]
        # hMod is ignored for LL hooks (the callback lives in this process);
        # pass the real module handle anyway for older-Windows friendliness.
        self._hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL, self._proc,
            kernel32.GetModuleHandleW(None), 0)
        return bool(self._hook)

    def _pump(self):
        user32 = ctypes.windll.user32
        msg = ctypes.wintypes.MSG()
        while self._running:
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r == 0 or r == -1:      # WM_QUIT or error
                return
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _uninstall(self):
        hook, self._hook = self._hook, None
        if hook:
            try:
                ctypes.windll.user32.UnhookWindowsHookEx(hook)
            except Exception:
                pass
        self._proc = None


# ctypes.wintypes is imported lazily by ctypes on Windows; make it explicit so
# module import works predictably (and fails loudly off-Windows only at start()).
try:
    import ctypes.wintypes  # noqa: E402  (needed by _install/_pump)
except Exception:           # non-Windows: pure logic above still importable
    pass
