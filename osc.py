"""Minimal OSC 1.0 message encoding — pure functions, no sockets.

Flow's show-control action speaks OSC (Open Sound Control), the lingua franca
of lighting desks, media servers, QLab, Resolume, and TouchDesigner. This
module only builds the bytes; the UDP send lives in actions.build_deps behind
the same trusted-rule gate as the webhook. MIDI is deliberately NOT here —
it needs a native driver dependency and is documented as future work.

Wire format (OSC 1.0): address pattern, then a type-tag string starting with
',', then arguments — every string null-terminated and padded to a 4-byte
boundary, int32/float32 big-endian.
"""

import re
import struct


def _pad_string(value: str) -> bytes:
    raw = value.encode("utf-8") + b"\x00"
    if len(raw) % 4:
        raw += b"\x00" * (4 - len(raw) % 4)
    return raw


def encode_message(address, args=()) -> bytes:
    """Build one OSC message. Supported argument types: str, int, float."""
    if not isinstance(address, str) or not address.startswith("/"):
        raise ValueError("an OSC address must start with '/'")
    tags = ","
    payload = b""
    for arg in args:
        if isinstance(arg, bool):
            raise ValueError("OSC bool arguments are not supported")
        if isinstance(arg, str):
            tags += "s"
            payload += _pad_string(arg)
        elif isinstance(arg, int):
            tags += "i"
            payload += struct.pack(">i", arg)
        elif isinstance(arg, float):
            tags += "f"
            payload += struct.pack(">f", arg)
        else:
            raise ValueError(f"unsupported OSC argument type {type(arg)!r}")
    return _pad_string(address) + _pad_string(tags) + payload


_TARGET_RE = re.compile(
    r"^(?P<host>[A-Za-z0-9_.-]+):(?P<port>\d{1,5})(?P<address>/\S*)$")


def parse_target(target):
    """Split '127.0.0.1:53000/cue/go' into (host, port, address).
    Raises ValueError with a human message on anything malformed."""
    m = _TARGET_RE.match((target or "").strip())
    if not m:
        raise ValueError(
            "OSC target must look like host:port/address — e.g. "
            "127.0.0.1:53000/cue/go")
    port = int(m.group("port"))
    if not 1 <= port <= 65535:
        raise ValueError(f"port {port} is out of range")
    return m.group("host"), port, m.group("address")
