import numpy as np

from tts import playback
from tts.types import AudioChunk, CancellationToken


class Stream:
    def __init__(self):
        self.writes = []
        self.started = False
        self.closed = False

    def start(self):
        self.started = True

    def write(self, samples):
        self.writes.append(samples.copy())

    def stop(self):
        pass

    def close(self):
        self.closed = True

    def abort(self):
        pass


def test_playback_uses_short_responsive_blocks(monkeypatch):
    stream = Stream()
    monkeypatch.setattr(
        playback.sd, "OutputStream", lambda **kwargs: stream)
    controller = playback.TTSPlaybackController()
    started = []
    controller.play(
        [AudioChunk(np.ones(6_001, dtype=np.float32))],
        cancellation_token=CancellationToken(),
        on_started=lambda: started.append(True),
    )

    assert started == [True]
    assert [len(block) for block in stream.writes] == [2400, 2400, 1201]
    assert stream.started and stream.closed
    assert all(len(block) <= playback.PLAYBACK_BLOCK_SAMPLES
               for block in stream.writes)
