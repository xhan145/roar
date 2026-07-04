"""Always-on-top dictation pill: live waveform + streaming text preview.

Tk runs on its own thread; every Tk touch happens there (commands posted via
a queue, drained by a 33 ms tick). The overlay is cosmetic — every public
method is exception-proof and the app never depends on it.
"""
import queue
import threading
from collections import deque

PILL = "#FFFFFF"
PILL_BORDER = "#E4DEF7"
BAR_ACTIVE = "#A78BFA"   # recording
BAR_IDLE = "#DDD6FE"     # transcribing / resting
TEXT = "#4C4568"
TRANS_KEY = "#010203"   # transparentcolor => rounded pill corners
W, H = 360, 44
N_BARS = 12
BAR_AREA_H = 20
BAR_W, BAR_STEP = 4, 7
CLUSTER_W = N_BARS * BAR_STEP - (BAR_STEP - BAR_W)  # 81


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
    def __init__(self):
        self.available = False
        self._cmds = queue.Queue()
        self._levels = deque(maxlen=N_BARS)
        self._thread = None
        self._mode = "hidden"
        self._partial = ""
        self._visible = False

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
            x = (root.winfo_screenwidth() - W) // 2
            y = root.winfo_screenheight() - 140
            root.geometry(f"{W}x{H}+{x}+{y}")
            canvas = tk.Canvas(root, width=W, height=H, bg=TRANS_KEY,
                               highlightthickness=0)
            canvas.pack()
            import tkinter.font as tkfont
            self._font = tkfont.Font(family="Segoe UI", size=10)
            self._root, self._canvas = root, canvas
            self.available = True
            root.after(33, self._tick)
            root.mainloop()
        except Exception as e:
            self.available = False
            print(f"ROAR: overlay unavailable: {e}", flush=True)

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
            # Adaptive cadence: 30 fps only while visible. Hidden/disabled the
            # thread idles at 4 Hz, so keeping the overlay always-constructed
            # (for instant enable from Settings) costs effectively nothing.
            self._root.after(33 if self._visible else 250, self._tick)
        except Exception:
            pass

    def _draw(self):
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
            self._visible = True
            self._root.deiconify()
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
        def f():
            self._visible = False
            self._mode = "hidden"
            self._partial = ""
            self._root.withdraw()
        self._post(f)

    def stop(self):
        def f():
            self._root.quit()
        self._post(f)
