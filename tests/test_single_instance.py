import pytest

pytest.importorskip("fcntl")

import single_instance


def test_linux_flock_first_acquires_second_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(single_instance.platform_id, "is_linux", lambda: True)
    monkeypatch.setattr(single_instance, "_lock_path", lambda: str(tmp_path / "roar.lock"))
    assert single_instance.acquire() is True    # first wins
    # second acquire from a fresh handle must fail while the first is held
    assert single_instance._acquire_linux(fresh=True) is False
