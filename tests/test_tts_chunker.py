import pytest

from tts.chunker import chunk_text, normalize_text


def test_chunker_preserves_abbreviations_and_punctuation():
    chunks = chunk_text(
        "Dr. Rivera arrived at 9 a.m. She brought notes. "
        "The notes were complete.",
        target_chars=45,
        max_chars=80,
    )
    assert "Dr." in chunks[0]
    assert "a.m." in " ".join(chunks)
    assert "".join(chunks).replace(" ", "") == (
        "Dr. Rivera arrived at 9 a.m. She brought notes. "
        "The notes were complete.").replace(" ", "")
    assert all(chunk[-1] in ".!?" for chunk in chunks)


def test_chunker_handles_unicode_paragraphs_and_lists():
    text = "Café notes:\n\n• First item 😀\n• Second item\n\n最後の段落です。"
    chunks = chunk_text(text, target_chars=80, max_chars=120)
    assert chunks
    assert "Café" in chunks[0]
    assert "😀" in " ".join(chunks)
    assert "最後" in " ".join(chunks)


def test_chunker_splits_oversized_input_without_tiny_fragments():
    chunks = chunk_text("word " * 300, target_chars=120, max_chars=160)
    assert 2 < len(chunks) < 20
    assert all(1 <= len(chunk) <= 160 for chunk in chunks)


def test_chunker_rejects_empty_and_pathological_input():
    with pytest.raises(ValueError, match="empty"):
        normalize_text("\x00 \n")
    with pytest.raises(ValueError, match="exceeds"):
        chunk_text("x" * 101, input_limit=100)


def test_chunker_removes_control_characters_but_keeps_line_breaks():
    assert normalize_text("hello\x07\nworld") == "hello\nworld"
