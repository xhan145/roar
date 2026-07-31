"""Always-on-top dictation pill + movable mic fob.

Idle, the window collapses to a small round mic dot (the fob): tap it to
toggle hands-free dictation, drag it anywhere (position persists via the
on_move callback), right-click for quick actions. While dictating it expands
into the waveform pill, centred on wherever the fob sits.

Tk runs on its own thread; every Tk touch happens there (commands posted via
a queue, drained by a tick). The overlay is cosmetic-plus — every public
method and every mouse handler is exception-proof, and dictation never
depends on it. Clicking the fob must NEVER steal keyboard focus from the app
being dictated into: the toplevel gets WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW.
If that style cannot be applied, tap/menu are disabled (drag still works)
rather than risk typing into the wrong window.
"""
import queue
import threading
from collections import deque

import fob
import platform_id

PILL = "#FFFFFF"
PILL_BORDER = "#E4DEF7"
BAR_ACTIVE = "#A78BFA"   # recording
BAR_IDLE = "#DDD6FE"     # transcribing / resting
TEXT = "#4C4568"
TRANS_KEY = "#010203"   # transparentcolor => rounded pill corners
W, H = 360, 44
DOT = 34                 # fob (idle) window size
N_BARS = 12
BAR_AREA_H = 20
BAR_W, BAR_STEP = 4, 7
CLUSTER_W = N_BARS * BAR_STEP - (BAR_STEP - BAR_W)  # 81

_WS_EX_NOACTIVATE = 0x08000000
_WS_EX_TOOLWINDOW = 0x00000080
_GWL_EXSTYLE = -20


def bar_heights(levels, n=N_BARS, h=BAR_AREA_H):
    vals = list(levels)[-n:]
    vals = [0.0] * (n - len(vals)) + vals
    return [max(2, int(v * h)) for v in vals]


def tail_text(text, max_chars=52):
    text = " ".join((text or "").split())
    if len(text) <= max_chars:
        return text
    return "…" + text[-(max_chars - 1):]


def bar_cluster_x(has_text, w=W):
    """Bars hug the left when text shares the row, center otherwise."""
    return 18 if has_text else (w - CLUSTER_W) // 2


def fit_tail(text, budget_px, measure):
    """Shave chars off the head until the text fits budget_px (measured in
    real font pixels) — char-count truncation alone overflows on wide glyphs."""
    while len(text) > 2 and measure(text) > budget_px:
        text = "…" + (text[2:] if text.startswith("…") else text[1:])
    return text


class Overlay:
    def __init__(self, on_tap=None, on_menu=None, on_move=None):
        self.available = False
        self.interactive = False    # False until NOACTIVATE is confirmed
        self._on_tap = on_tap
        self._on_menu = on_menu
        self._on_move = on_move
        self._cmds = queue.Queue()
        self._levels = deque(maxlen=N_BARS)
        self._thread = None
        self._mode = "hidden"       # hidden | dot | recording | transcribing
        self._partial = ""
        self._visible = False
        self._fob_enabled = False
        self._fob_pos = None        # (x, y) of the DOT window, persisted
        self._gesture = fob.GestureClassifier()
        self._drag_origin = None    # window (x, y) at press time

    # -- thread-side ------------------------------------------------------
    def _run(self):
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            try:
                root.attributes("-transparentcolor", TRANS_KEY)
            except Exception:
                pass
            self._bounds = self._screen_bounds(root)
            x, y = fob.default_pos(self._bounds, DOT, DOT)
            self._fob_pos = (x, y)
            root.geometry(f"{DOT}x{DOT}+{x}+{y}")
            canvas = tk.Canvas(root, width=W, height=H, bg=TRANS_KEY,
                               highlightthickness=0)
            canvas.pack()
            import tkinter.font as tkfont
            self._font = tkfont.Font(family="Segoe UI", size=10)
            self._root, self._canvas = root, canvas
            self.interactive = self._make_noactivate(root)
            self._bind_mouse(canvas)
            self.available = True
            root.after(33, self._tick)
            root.mainloop()
        except Exception as e:
            self.available = False
            print(f"ROAR: overlay unavailable: {e}", flush=True)

    @staticmethod
    def _screen_bounds(root):
        """Virtual-screen bounds (left, top, right, bottom) — all monitors."""
        if platform_id.is_windows():
            try:
                import ctypes
                gm = ctypes.windll.user32.GetSystemMetrics
                left, top = gm(76), gm(77)          # SM_X/YVIRTUALSCREEN
                return (left, top, left + gm(78), top + gm(79))
            except Exception:
                pass
        return (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())

    @staticmethod
    def _make_noactivate(root):
        """Apply WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW so clicks never move
        keyboard focus off the dictation target. Returns True when the fob may
        be interactive. Non-Windows: interactive without the style (the Linux
        port is experimental and X11 focus semantics differ)."""
        if not platform_id.is_windows():
            return True
        try:
            import ctypes
            user32 = ctypes.windll.user32
            root.update_idletasks()
            hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
            get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            style = get_long(hwnd, _GWL_EXSTYLE)
            set_long(hwnd, _GWL_EXSTYLE,
                     style | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW)
            applied = get_long(hwnd, _GWL_EXSTYLE)
            if not (applied & _WS_EX_NOACTIVATE):
                raise OSError("style did not stick")
            return True
        except Exception as e:
            print(f"ROAR: fob is display-only (no-activate failed: {e})",
                  flush=True)
            return False

    def _bind_mouse(self, canvas):
        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_drag)
        canvas.bind("<ButtonRelease-1>", self._on_release)
        canvas.bind("<ButtonPress-3>", self._on_context)

    # mouse handlers run on the Tk thread; each is exception-proof so a
    # callback bug can degrade the fob but never kill the overlay
    def _on_press(self, ev):
        try:
            self._gesture.press(ev.x_root, ev.y_root)
            self._drag_origin = (self._root.winfo_x(), self._root.winfo_y())
        except Exception:
            pass

    def _on_drag(self, ev):
        try:
            offset = self._gesture.move(ev.x_root, ev.y_root)
            if offset is None or self._drag_origin is None:
                return
            w, h = self._win_size()
            x, y = fob.clamp_pos(self._drag_origin[0] + offset[0],
                                 self._drag_origin[1] + offset[1],
                                 w, h, self._bounds)
            self._root.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _on_release(self, ev):
        try:
            gesture = self._gesture.release()
            if gesture == "drag":
                # persist the DOT-equivalent anchor: when released while the
                # pill is expanded, keep the pill's centre as the dot's centre
                x, y = self._root.winfo_x(), self._root.winfo_y()
                w, h = self._win_size()
                self._fob_pos = fob.clamp_pos(x + w // 2 - DOT // 2,
                                              y + h // 2 - DOT // 2,
                                              DOT, DOT, self._bounds)
                if self._on_move:
                    self._safe_callback(self._on_move, *self._fob_pos)
            elif gesture == "tap" and self.interactive and self._on_tap:
                self._safe_callback(self._on_tap)
        except Exception:
            pass

    def _on_context(self, ev):
        if not (self.interactive and self._on_menu):
            return
        try:
            import tkinter as tk
            menu = tk.Menu(self._root, tearoff=0)
            for label, action in (("Scratch that", "scratch"),
                                  ("Read selected text", "read_selected"),
                                  ("Open Settings", "settings"),
                                  ("Hide fob", "hide")):
                menu.add_command(
                    label=label,
                    command=lambda a=action: self._safe_callback(
                        self._on_menu, a))
            menu.tk_popup(ev.x_root, ev.y_root)
            menu.grab_release()
        except Exception:
            pass

    @staticmethod
    def _safe_callback(fn, *args):
        try:
            fn(*args)
        except Exception as e:
            print(f"ROAR: fob callback failed: {e}", flush=True)

    def _win_size(self):
        return (DOT, DOT) if self._mode == "dot" else (W, H)

    def _apply_mode(self):
        """Size + place the window for the current mode (Tk thread only)."""
        if self._mode == "dot":
            x, y = self._fob_pos
            self._root.geometry(f"{DOT}x{DOT}+{x}+{y}")
            self._visible = True
            self._root.deiconify()
        elif self._mode in ("recording", "transcribing"):
            x, y = fob.expand_anchor(self._fob_pos[0], self._fob_pos[1],
                                     DOT, W, H, self._bounds)
            self._root.geometry(f"{W}x{H}+{x}+{y}")
            self._visible = True
            self._root.deiconify()
        else:
            self._visible = False
            self._root.withdraw()

    def _tick(self):
        try:
            while True:
                self._cmds.get_nowait()()
        except queue.Empty:
            pass
        except Exception:
            pass
        if self._visible:
            try:
                self._draw()
            except Exception:
                pass
        try:
            # 30 fps only while the animated pill shows; the static dot and
            # the hidden state idle at 4 Hz.
            fast = self._visible and self._mode != "dot"
            self._root.after(33 if fast else 250, self._tick)
        except Exception:
            pass

    def _draw(self):
        if self._mode == "dot":
            self._draw_dot()
            return
        c = self._canvas
        c.delete("all")
        r = H // 2  # capsule: fully rounded ends
        c.create_polygon(
            r, 2, W - r, 2, W - 2, 2, W - 2, r, W - 2, H - r, W - 2, H - 2,
            W - r, H - 2, r, H - 2, 2, H - 2, 2, H - r, 2, r, 2, 2,
            smooth=True, fill=PILL, outline=PILL_BORDER)
        txt = self._partial
        if self._mode == "transcribing":
            txt = (txt + " …") if txt else "…"
        color = BAR_ACTIVE if self._mode == "recording" else BAR_IDLE
        heights = bar_heights(self._levels)
        mid = H // 2
        x_start = bar_cluster_x(bool(txt))
        for i, bh in enumerate(heights):
            x0 = x_start + i * BAR_STEP
            c.create_rectangle(x0, mid - bh // 2, x0 + BAR_W, mid + bh // 2,
                               fill=color, outline="")
        if txt:
            text_x = x_start + CLUSTER_W + 14
            shown = fit_tail(tail_text(txt, 34), W - text_x - 16,
                             self._font.measure)
            c.create_text(text_x, mid, text=shown, fill=TEXT,
                          font=self._font, anchor="w")

    def _draw_dot(self):
        c = self._canvas
        c.delete("all")
        d = DOT
        c.create_oval(2, 2, d - 2, d - 2, fill=PILL, outline=BAR_ACTIVE,
                      width=2)
        # mic glyph: capsule body + stand
        cx = d // 2
        c.create_oval(cx - 4, 8, cx + 4, 19, fill=BAR_ACTIVE, outline="")
        c.create_arc(cx - 7, 12, cx + 7, 24, start=180, extent=180,
                     style="arc", outline=BAR_ACTIVE, width=2)
        c.create_line(cx, 24, cx, 27, fill=BAR_ACTIVE, width=2)

    # -- public, thread-safe, exception-proof ------------------------------
    def _post(self, fn):
        try:
            self._cmds.put(fn)
        except Exception:
            pass

    def start(self):
        try:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        except Exception as e:
            print(f"ROAR: overlay thread failed: {e}", flush=True)

    def set_fob(self, enabled, pos=None):
        """Show/hide the idle mic dot; `pos` is a persisted [x, y] or None."""
        def f():
            self._fob_enabled = bool(enabled)
            valid = fob.validate_pos(pos, DOT, DOT, self._bounds)
            if valid:
                self._fob_pos = valid
            if self._mode in ("hidden", "dot"):
                self._mode = "dot" if self._fob_enabled else "hidden"
                self._apply_mode()
        self._post(f)

    def push_level(self, v):
        try:
            self._levels.append(float(v))
        except Exception:
            pass

    def show_recording(self):
        def f():
            self._levels.clear()
            self._mode = "recording"
            self._partial = ""
            self._apply_mode()
        self._post(f)

    def set_partial(self, text):
        def f():
            self._partial = text or ""
        self._post(f)

    def show_transcribing(self):
        def f():
            self._mode = "transcribing"
        self._post(f)

    def hide(self):
        """Dictation finished: collapse back to the fob dot (or vanish when
        the fob is disabled — exactly the old behavior)."""
        def f():
            self._partial = ""
            self._mode = "dot" if self._fob_enabled else "hidden"
            self._apply_mode()
        self._post(f)

    def stop(self):
        def f():
            self._root.quit()
        self._post(f)
