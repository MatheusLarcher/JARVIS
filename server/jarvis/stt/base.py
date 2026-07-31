"""Interface de STT streaming. Trocar de motor = nova subclasse + registro em factory()."""
import numpy as np


class SttStream:
    """Uma elocução. Recebe PCM int16 16kHz em pedaços e emite parciais/final."""

    def feed(self, pcm: np.ndarray) -> str | None:
        """Alimenta áudio; retorna transcrição parcial quando houver novidade."""
        raise NotImplementedError

    def finish(self) -> str:
        """Encerra e retorna a transcrição final."""
        raise NotImplementedError


class SttEngine:
    async def load(self):
        raise NotImplementedError

    def new_stream(self) -> SttStream:
        raise NotImplementedError


def factory(name: str) -> SttEngine:
    if name == "nemotron":
        from .nemotron import NemotronStt
        return NemotronStt()
    if name == "dummy":
        from .dummy import DummyStt
        return DummyStt()
    raise ValueError(f"engine STT desconhecido: {name}")
