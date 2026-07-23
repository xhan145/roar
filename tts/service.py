"""Deterministic, cancellable orchestration for local synthesis and playback."""
from __future__ import annotations

import queue
import threading
import time

from .chunker import chunk_text, normalize_text
from .playback import TTSPlaybackController
from .types import (
    CancellationToken,
    MAX_SPEED,
    MIN_SPEED,
    TTSConfig,
    TTSCancelled,
    TTSRequest,
    TTSState,
)
from .voices import get_voice

_ALLOWED = {
    TTSState.UNAVAILABLE: {TTSState.UNLOADED, TTSState.LOADING},
    TTSState.UNLOADED: {TTSState.UNAVAILABLE, TTSState.LOADING,
                        TTSState.STOPPING},
    TTSState.LOADING: {TTSState.READY, TTSState.ERROR, TTSState.STOPPING,
                       TTSState.UNAVAILABLE},
    TTSState.READY: {TTSState.SYNTHESIZING, TTSState.LOADING,
                     TTSState.STOPPING, TTSState.UNLOADED, TTSState.ERROR,
                     TTSState.UNAVAILABLE},
    TTSState.SYNTHESIZING: {TTSState.PLAYING, TTSState.STOPPING,
                            TTSState.ERROR, TTSState.READY},
    TTSState.PLAYING: {TTSState.PAUSED, TTSState.SYNTHESIZING,
                       TTSState.STOPPING, TTSState.READY, TTSState.ERROR},
    TTSState.PAUSED: {TTSState.PLAYING, TTSState.STOPPING, TTSState.ERROR},
    TTSState.STOPPING: {TTSState.READY, TTSState.UNLOADED,
                        TTSState.UNAVAILABLE, TTSState.ERROR},
    TTSState.ERROR: {TTSState.LOADING, TTSState.STOPPING, TTSState.UNLOADED,
                     TTSState.UNAVAILABLE, TTSState.READY},
}


class TTSService:
    """Owns one engine and serializes all speech away from the UI thread."""

    def __init__(
        self,
        engine,
        config: TTSConfig,
        *,
        playback=None,
        listener=None,
        logger=None,
        queue_size=8,
    ):
        self.engine = engine
        self.config = config
        self.playback = playback or TTSPlaybackController()
        self.listener = listener
        self.logger = logger or (lambda event, fields: None)
        self._state_lock = threading.RLock()
        self._state = (TTSState.UNLOADED if engine.is_available()
                       else TTSState.UNAVAILABLE)
        self._jobs = queue.Queue(maxsize=max(1, queue_size))
        self._stop_event = threading.Event()
        self._token = None
        self._generation = 0
        self._loaded = False
        self._last_text = None
        self._last_request = None
        self._last_active = time.monotonic()
        self._worker = threading.Thread(
            target=self._run, name="ROAR-TTS-service", daemon=True)
        self._worker.start()
        self._publish(self._state, {})
        if config.enabled and config.preload_model:
            self.preload()

    @property
    def state(self):
        with self._state_lock:
            return self._state

    @property
    def active(self):
        return self.state in {
            TTSState.LOADING, TTSState.SYNTHESIZING, TTSState.PLAYING,
            TTSState.PAUSED, TTSState.STOPPING,
        }

    def update_config(self, config: TTSConfig):
        previous = self.config
        self.config = config
        if (previous.model_path != config.model_path
                or previous.language != config.language):
            self.stop(clear_last=False)
            self.engine.unload()
            self._loaded = False
            target = (TTSState.UNLOADED if self.engine.is_available()
                      else TTSState.UNAVAILABLE)
            self._force_state(target)
        if config.enabled and config.preload_model and not self._loaded:
            self.preload()

    def preload(self):
        if not self.config.enabled:
            return False
        return self._put(("preload", None), replace=False)

    def speak(
        self,
        text,
        *,
        source="typed",
        voice=None,
        speed=None,
        language=None,
        volume=None,
        output_device=None,
        remember=True,
        on_complete=None,
    ):
        if not self.config.enabled:
            raise RuntimeError("ROAR Read Aloud is disabled")
        clean = normalize_text(text)
        language = language or self.config.language
        selected = get_voice(voice or self.config.voice, language)
        speed = self.config.speed if speed is None else float(speed)
        if not MIN_SPEED <= speed <= MAX_SPEED:
            raise ValueError("speech speed is out of range")
        volume = self.config.volume if volume is None else float(volume)
        if not 0.0 <= volume <= 1.0:
            raise ValueError("speech volume is out of range")
        request = TTSRequest(
            text=clean,
            voice=selected.voice_id,
            speed=speed,
            language=language,
            volume=volume,
            output_device=(self.config.output_device
                           if output_device is None else output_device),
            source=source,
        )
        if remember and source in ("typed", "clipboard", "selected", "preview"):
            self._last_text = clean
            self._last_request = request
        self.stop(clear_last=False)
        return self._put(("speak", (request, on_complete)), replace=True)

    def repeat_last(self):
        request = self._last_request
        if not request or not self._last_text:
            return False
        return self.speak(
            self._last_text,
            source="repeat",
            voice=request.voice,
            speed=request.speed,
            language=request.language,
            volume=request.volume,
            output_device=request.output_device,
            remember=False,
        )

    def pause(self):
        if self.state != TTSState.PLAYING:
            return False
        self.playback.pause()
        self._transition(TTSState.PAUSED)
        self._log("tts.playback.paused")
        return True

    def resume(self):
        if self.state != TTSState.PAUSED:
            return False
        self.playback.resume()
        self._transition(TTSState.PLAYING)
        self._log("tts.playback.resumed")
        return True

    def pause_resume(self):
        return self.resume() if self.state == TTSState.PAUSED else self.pause()

    def stop(self, *, clear_last=False):
        with self._state_lock:
            self._generation += 1
            token = self._token
        if token is not None:
            token.cancel()
        try:
            self.engine.cancel()
        except Exception:
            pass
        self.playback.stop()
        self._drain_jobs()
        if clear_last:
            self._last_text = self._last_request = None
        if self.active:
            self._force_state(TTSState.STOPPING)
            self._log("tts.playback.cancelled")
        return True

    cancel = stop

    def unload(self):
        self.stop(clear_last=False)
        try:
            self.engine.unload()
        finally:
            self._loaded = False
            self._force_state(TTSState.UNLOADED if self.engine.is_available()
                              else TTSState.UNAVAILABLE)
        return True

    def shutdown(self, timeout=5):
        self.stop(clear_last=True)
        self._stop_event.set()
        self._put(("shutdown", None), replace=True)
        self._worker.join(timeout=timeout)
        try:
            self.engine.unload()
        finally:
            self._loaded = False
            self._force_state(TTSState.UNLOADED)

    def _run(self):
        while not self._stop_event.is_set():
            try:
                kind, payload = self._jobs.get(timeout=0.25)
            except queue.Empty:
                self._maybe_unload_idle()
                continue
            if kind == "shutdown":
                break
            if kind == "preload":
                try:
                    self._ensure_loaded()
                except Exception:
                    pass
            elif kind == "speak":
                request, callback = payload
                self._run_request(request, callback)

    def _ensure_loaded(self):
        if self._loaded:
            return
        if not self.engine.is_available():
            self._force_state(TTSState.UNAVAILABLE)
            raise RuntimeError("local voice model or runtime is unavailable")
        self._transition(TTSState.LOADING)
        self._log("tts.model.load.started")
        started = time.perf_counter()
        try:
            self.engine.load(self.config)
            self._loaded = True
            self._last_active = time.monotonic()
            self._transition(TTSState.READY)
            self._log("tts.model.load.completed",
                      elapsed_ms=round((time.perf_counter() - started) * 1000))
        except Exception as exc:
            self._loaded = False
            self._force_state(TTSState.ERROR, error_category=_category(exc))
            self._log("tts.model.load.failed", error_category=_category(exc))
            raise

    def _run_request(self, request, callback):
        with self._state_lock:
            generation = self._generation
            token = CancellationToken()
            self._token = token
        outcome = "failed"
        started = time.perf_counter()
        try:
            self._ensure_loaded()
            if generation != self._generation:
                raise TTSCancelled()
            pieces = chunk_text(request.text)
            self._transition(TTSState.SYNTHESIZING)
            self._log("tts.synthesis.started",
                      character_count=len(request.text), chunk_count=len(pieces))

            def generated():
                sequence = 0
                for piece in pieces:
                    token.raise_if_cancelled()
                    for audio in self.engine.synthesize(
                        piece,
                        voice=request.voice,
                        speed=request.speed,
                        language=request.language,
                        cancellation_token=token,
                    ):
                        token.raise_if_cancelled()
                        if generation != self._generation:
                            raise TTSCancelled()
                        yield type(audio)(
                            audio.samples, audio.sample_rate, sequence)
                        sequence += 1

            def started_playback():
                if generation == self._generation:
                    self._transition(TTSState.PLAYING)
                    self._log("tts.playback.started")

            self.playback.play(
                generated(),
                cancellation_token=token,
                volume=request.volume,
                device=request.output_device,
                on_started=started_playback,
            )
            token.raise_if_cancelled()
            outcome = "completed"
            elapsed = round((time.perf_counter() - started) * 1000)
            metrics = getattr(self.engine, "metrics", {}) or {}
            safe_metrics = {
                key: metrics.get(key) for key in (
                    "first_audio_ms", "audio_duration_ms", "real_time_factor")
                if metrics.get(key) is not None
            }
            self._log("tts.synthesis.completed", elapsed_ms=elapsed,
                      chunk_count=len(pieces), **safe_metrics)
            self._log("tts.playback.completed")
        except TTSCancelled:
            outcome = "cancelled"
            self._log("tts.synthesis.cancelled")
        except Exception as exc:
            category = _category(exc)
            self._force_state(TTSState.ERROR, error_category=category)
            self._log("tts.playback.failed", error_category=category)
        finally:
            with self._state_lock:
                if self._token is token:
                    self._token = None
            self._last_active = time.monotonic()
            if generation == self._generation and self.state != TTSState.ERROR:
                self._force_state(TTSState.READY if self._loaded
                                  else TTSState.UNLOADED)
            elif self.state == TTSState.STOPPING:
                self._force_state(TTSState.READY if self._loaded
                                  else TTSState.UNLOADED)
            if callback:
                try:
                    callback(outcome)
                except Exception:
                    pass

    def _maybe_unload_idle(self):
        minutes = self.config.unload_after_idle_minutes
        if (not self._loaded or minutes <= 0 or self.active
                or time.monotonic() - self._last_active < minutes * 60):
            return
        try:
            self.engine.unload()
        finally:
            self._loaded = False
            self._force_state(TTSState.UNLOADED)

    def _put(self, item, *, replace):
        if replace:
            self._drain_jobs()
        try:
            self._jobs.put_nowait(item)
            return True
        except queue.Full:
            return False

    def _drain_jobs(self):
        try:
            while True:
                self._jobs.get_nowait()
        except queue.Empty:
            pass

    def _transition(self, new_state, **fields):
        with self._state_lock:
            current = self._state
            if new_state == current:
                return
            if new_state not in _ALLOWED[current]:
                raise RuntimeError(
                    f"invalid TTS state transition {current.value} -> "
                    f"{new_state.value}")
            self._state = new_state
        self._publish(new_state, fields)

    def _force_state(self, state, **fields):
        with self._state_lock:
            self._state = state
        self._publish(state, fields)

    def _publish(self, state, fields):
        if self.listener:
            try:
                self.listener(state, dict(fields))
            except Exception:
                pass

    def _log(self, event, **fields):
        self.logger(event, fields)


def _category(exc):
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "device" in text or "portaudio" in text:
        return "audio_device"
    if "model" in text or "runtime" in text or "worker" in text:
        return "engine_unavailable"
    if "hash" in text:
        return "model_integrity"
    if "cancel" in name:
        return "cancelled"
    return "internal"
