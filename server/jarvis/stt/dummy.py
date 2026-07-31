"""STT de desenvolvimento: não transcreve, serve pra testar o fluxo sem GPU/modelo."""
import numpy as np

from .base import SttEngine, SttStream


class DummyStream(SttStream):
    def __init__(self):
        self.samples = 0

    def feed(self, pcm: np.ndarray) -> str | None:
        self.samples += len(pcm)
        return None

    def finish(self) -> str:
        return ""


class DummyStt(SttEngine):
    async def load(self):
        pass

    def new_stream(self) -> SttStream:
        return DummyStream()
