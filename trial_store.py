"""Trial persistence: protected file + registry marker + rollback bookkeeping.

The Full-Feature Trial record (see trial.py) is stored in two lightweight
places so accidental deletion or an uninstall/reinstall does not quietly grant
a second trial:

- a JSON envelope at paths.trial_state_path() — beside license.json in
  %APPDATA%\\ROAR, deliberately separate from history/audio/vocabulary, so
  privacy resets and normal upgrades never touch it;
- an HKCU registry marker holding a copy of the same envelope.

The envelope's HMAC key is protected with Windows DPAPI when available; on
other platforms (and when DPAPI fails) it falls back to a plainly stored key.
This is honest best-effort tamper resistance against accidental resets and
trivial deletion — it is not, and is never advertised as, offline DRM.

No network. No transcripts, audio, history, clipboard, vocabulary, or window
titles — the envelope carries trial bookkeeping only. winreg/ctypes are
imported lazily inside functions so cross-platform imports stay clean.
"""

import base64
import json
import logging
import os
import secrets
import tempfile
from datetime import timedelta

import paths
import trial

_log = logging.getLogger("roar.trial")

ENVELOPE_VERSION = 1
# How coarsely the anti-rollback mark is persisted. Far finer than a 14-day
# trial needs, and it keeps the dictation path off the disk and the registry.
LAST_SEEN_GRANULARITY = timedelta(hours=1)
_REGISTRY_KEY = r"Software\ROAR"
_REGISTRY_VALUE = "TrialState"


class NullProtection:
    """Identity protection — non-Windows platforms and tests."""

    name = "none"

    def protect(self, data):
        return data

    def unprotect(self, blob):
        return blob


class DpapiProtection:
    """Windows DPAPI (CryptProtectData), current-user scope. Lazy ctypes."""

    name = "dpapi"

    def _crypt(self, data, decrypt):
        import ctypes
        import ctypes.wintypes as wt

        class _Blob(ctypes.Structure):
            _fields_ = [("cbData", wt.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]

        buf = ctypes.create_string_buffer(data, len(data))
        blob_in = _Blob(len(data), ctypes.cast(
            buf, ctypes.POINTER(ctypes.c_char)))
        blob_out = _Blob()
        fn = (ctypes.windll.crypt32.CryptUnprotectData if decrypt
              else ctypes.windll.crypt32.CryptProtectData)
        if not fn(ctypes.byref(blob_in), None, None, None, None, 0,
                  ctypes.byref(blob_out)):
            raise OSError("DPAPI call failed")
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)

    def protect(self, data):
        return self._crypt(data, decrypt=False)

    def unprotect(self, blob):
        return self._crypt(blob, decrypt=True)


def default_protection():
    return DpapiProtection() if os.name == "nt" else NullProtection()


class WindowsRegistryMarker:
    """HKCU marker so file deletion alone cannot reset the trial. Lazy winreg;
    every operation degrades to a no-op off Windows or on registry errors."""

    def __init__(self, value_name=_REGISTRY_VALUE):
        self._value = value_name

    def read(self):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_KEY) as k:
                raw, kind = winreg.QueryValueEx(k, self._value)
            if kind != winreg.REG_SZ:
                return None
            return json.loads(raw)
        except (ImportError, OSError, ValueError):
            return None

    def write(self, envelope):
        try:
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                  _REGISTRY_KEY) as k:
                winreg.SetValueEx(k, self._value, 0, winreg.REG_SZ,
                                  json.dumps(envelope))
        except (ImportError, OSError, TypeError):
            _log.warning("trial marker write failed (non-fatal)")

    def delete(self):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, self._value)
        except (ImportError, OSError):
            pass


def default_marker():
    return WindowsRegistryMarker() if os.name == "nt" else _NoMarker()


class _NoMarker:
    def read(self):
        return None

    def write(self, envelope):
        pass


class TrialService:
    """All trial reads and writes go through here.

    Injectable seams (`path`, `marker`, `protection`) exist for tests and are
    the ONLY overrides — there is no environment-variable bypass, no editable
    duration, and no way to restart a trial that has material on disk.
    """

    def __init__(self, path=None, marker=None, protection=None):
        self._path = path or paths.trial_state_path()
        self._marker = marker if marker is not None else default_marker()
        self._protection = protection or default_protection()

    # -- envelope plumbing ---------------------------------------------------

    def _decode(self, envelope):
        """(key, signed_record) from an envelope, or None if unusable."""
        if not isinstance(envelope, dict):
            return None
        if envelope.get("schema_version") != ENVELOPE_VERSION:
            return None
        record = envelope.get("record")
        try:
            key_blob = base64.b64decode(envelope["key_b64"], validate=True)
        except (KeyError, TypeError, ValueError):
            return None
        key = None
        if envelope.get("key_protection") == self._protection.name:
            try:
                key = self._protection.unprotect(key_blob)
            except Exception:
                key = None
        elif envelope.get("key_protection") == "none":
            key = key_blob
        if key is None:
            return None
        if not trial.verify_record(record, key):
            return None
        stripped = {k: v for k, v in record.items() if k != "signature"}
        if trial.validate_record(stripped) is None:
            return None
        return key, record

    def _encode(self, key, record):
        """Re-sign on every write: the mutable fields are inside the HMAC, so
        hand-editing last_seen or the notice flag invalidates the record."""
        signed = trial.sign_record(
            {k: v for k, v in record.items() if k != "signature"}, key)
        try:
            blob, kind = self._protection.protect(key), self._protection.name
        except Exception:
            blob, kind = key, "none"
        return {
            "schema_version": ENVELOPE_VERSION,
            "key_protection": kind,
            "key_b64": base64.b64encode(blob).decode("ascii"),
            "record": signed,
        }

    def _read_file(self):
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def _looks_like_a_trial(self, envelope):
        """True when an envelope plainly holds a structurally sound record we
        simply cannot VERIFY (e.g. DPAPI can no longer decrypt the key after
        an OS reinstall). Such a record must never be treated as absent — it
        may not grant anything, but it must not grant a fresh trial either."""
        if not isinstance(envelope, dict):
            return False
        record = envelope.get("record")
        if not isinstance(record, dict):
            return False
        stripped = {k: v for k, v in record.items() if k != "signature"}
        return trial.validate_record(stripped) is not None

    def _file_has_material(self):
        try:
            return os.path.getsize(self._path) > 0
        except OSError:
            return False

    def _write_everywhere(self, envelope):
        try:
            directory = os.path.dirname(self._path) or "."
            os.makedirs(directory, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(envelope, fh)
                os.replace(tmp, self._path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        except OSError:
            _log.warning("trial state file write failed (non-fatal)")
        self._marker.write(envelope)

    def _load(self):
        """(key, record, unusable). record=None/unusable=False → not started;
        unusable=True → material exists somewhere but none of it is usable."""
        candidates = []
        material = False
        unverifiable = False
        self._needs_heal = False
        for envelope in (self._read_file(), self._marker.read()):
            if envelope is not None:
                material = True
            decoded = self._decode(envelope)
            if decoded is not None:
                candidates.append(decoded)
            else:
                # one store is gone or unreadable: if the other survives we
                # write it back ONCE, so deleting a copy heals rather than
                # quietly halving the protection
                self._needs_heal = True
                if self._looks_like_a_trial(envelope):
                    unverifiable = True
        material = material or self._file_has_material()
        if not candidates:
            # Nothing verified. A structurally sound but unverifiable record
            # (lost DPAPI key) reports as material so start() still refuses.
            return None, None, (material or unverifiable)
        # Earliest start wins — a later record can never short-circuit an
        # existing trial into a fresh one. The mutable fields are then merged
        # across BOTH stores so a newer high-water mark or a seen notice in
        # either copy is honoured (a single-store edit cannot rewind them).
        key, record = min(
            candidates,
            key=lambda kr: trial.parse_utc(kr[1]["started_at_utc"]))
        merged = dict(record)
        marks = [trial.parse_utc(r["last_seen_at_utc"]) for _k, r in candidates]
        merged["last_seen_at_utc"] = trial.format_utc(max(marks))
        merged["expired_notice_seen"] = any(
            bool(r.get("expired_notice_seen")) for _k, r in candidates)
        return key, merged, False

    # -- public API ----------------------------------------------------------

    def status(self, now=None):
        moment = now or trial.utc_now()
        key, record, unusable = self._load()
        if unusable:
            return trial.TrialStatus(trial.INVALID, None, None, 0, 0, False)
        if record is None:
            return trial.TrialStatus(trial.NOT_STARTED, None, None, 0, 0,
                                     False)
        status = trial.status_of(record, now=moment)
        advance = self._should_advance(status, record, moment)
        if advance:
            record = dict(record)
            record["last_seen_at_utc"] = trial.format_utc(
                min(moment, trial.parse_utc(record["expires_at_utc"])))
        if advance or getattr(self, "_needs_heal", False):
            self._write_everywhere(self._encode(key, record))
        return status

    @staticmethod
    def _should_advance(status, record, moment):
        """Persist the anti-rollback mark rarely and only while it matters.

        Writes are CLAMPED to the expiry instant (a mark beyond it carries no
        information but would wedge the trial after a bad clock reading) and
        rate-limited to a coarse dead-band, so a status read on the dictation
        path does not rewrite %APPDATA% and the registry every time. Once the
        trial is over the mark protects nothing, so nothing is written — and
        the record stops tracking when the user last dictated.
        """
        if status.state != trial.ACTIVE:
            return False
        last_seen = trial.parse_utc(record["last_seen_at_utc"])
        expires = trial.parse_utc(record["expires_at_utc"])
        if last_seen >= expires:
            return False
        return min(moment, expires) - last_seen >= LAST_SEEN_GRANULARITY

    def start(self, now=None):
        """Begin the 14-day trial — only if none was ever started here."""
        moment = now or trial.utc_now()
        _key, record, unusable = self._load()
        if unusable or record is not None:
            return self.status(now=moment)
        key = secrets.token_bytes(32)
        self._write_everywhere(
            self._encode(key, trial.new_record(now=moment)))
        return self.status(now=moment)

    def is_active(self, now=None):
        return self.status(now=now).state == trial.ACTIVE

    def days_remaining(self, now=None):
        return self.status(now=now).days_remaining

    def mark_expired_notice_seen(self):
        """Record that the one-time ended notice was shown. Returns True when
        the acknowledgement is safely stored, so callers can fall back to a
        process-level latch if the write failed."""
        key, record, unusable = self._load()
        if unusable or record is None:
            return False
        record = dict(record)
        record["expired_notice_seen"] = True
        self._write_everywhere(self._encode(key, record))
        _key, stored, _bad = self._load()
        return bool(stored and stored.get("expired_notice_seen"))
