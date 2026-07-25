import os

import pytest

from tts import kokoro_engine


@pytest.mark.skipif(os.name != "nt", reason="Windows process-tree behavior")
def test_force_termination_kills_the_worker_process_tree(monkeypatch):
    calls = []

    class Process:
        pid = 1234

        @staticmethod
        def poll():
            return None

        @staticmethod
        def terminate():
            raise AssertionError("tree termination should be attempted first")

    monkeypatch.setattr(
        kokoro_engine.subprocess, "run",
        lambda command, **kwargs: calls.append((command, kwargs)))
    engine = kokoro_engine.KokoroEngine(python_command=["python"])
    engine._process = Process()
    engine._terminate()

    assert calls[0][0] == [
        "taskkill", "/PID", str(Process.pid), "/T", "/F"]
    assert calls[0][1]["timeout"] == 5
