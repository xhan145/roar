"""OSC encoding: byte-exact against the OSC 1.0 spec, plus target parsing."""

import struct

import pytest

import osc


def test_address_only_message():
    msg = osc.encode_message("/go")
    #  /go\0  ,\0\0\0
    assert msg == b"/go\x00,\x00\x00\x00"


def test_string_argument_padded():
    msg = osc.encode_message("/cue", ["hi"])
    assert msg == b"/cue\x00\x00\x00\x00" + b",s\x00\x00" + b"hi\x00\x00"


def test_int_and_float_arguments_big_endian():
    msg = osc.encode_message("/x", [7, 1.5])
    tags = b",if\x00"
    assert msg == b"/x\x00\x00" + tags + struct.pack(">i", 7) + struct.pack(">f", 1.5)


def test_four_byte_alignment_always_holds():
    for addr in ("/a", "/ab", "/abc", "/abcd"):
        for arg in ("", "x", "xy", "xyz", "wxyz"):
            msg = osc.encode_message(addr, [arg])
            assert len(msg) % 4 == 0, (addr, arg)


def test_rejects_bad_address_and_types():
    with pytest.raises(ValueError):
        osc.encode_message("nope")
    with pytest.raises(ValueError):
        osc.encode_message("/x", [object()])
    with pytest.raises(ValueError):
        osc.encode_message("/x", [True])   # bools are ambiguous in OSC 1.0


def test_parse_target():
    assert osc.parse_target("127.0.0.1:53000/cue/go") == \
        ("127.0.0.1", 53000, "/cue/go")
    assert osc.parse_target("lighting-desk.local:8000/roar") == \
        ("lighting-desk.local", 8000, "/roar")


@pytest.mark.parametrize("bad", [
    "", "127.0.0.1/cue", "host:0/x", "host:99999/x", "host:53000",
    "host:53000cue", ":53000/x",
])
def test_parse_target_rejects(bad):
    with pytest.raises(ValueError):
        osc.parse_target(bad)
