"""STT híbrido: rápido nas parciais, preciso no final.

Motivo: são objetivos diferentes.
  - as PARCIAIS existem pra reconhecer "Jarvis" o quanto antes e acender o
    reator — precisam ser rápidas, erro não faz mal;
  - a transcrição FINAL vira comando — aí o que vale é acertar.

Medido neste projeto (RTX 5050): Nemotron 0,47s/frase com WER 0.016 (limpo) e
0.062 (com ruído); Whisper turbo 0,70s com WER 0.000 nos dois casos.
"""
import asyncio
import logging

import numpy as np

from .base import SttEngine, SttStream

log = logging.getLogger("jarvis.stt")


class HibridoStream(SttStream):
    def __init__(self, rapido: SttStream, preciso: SttStream, engine: "HibridoStt"):
        self.rapido = rapido
        self.preciso = preciso
        self.engine = engine

    def prime(self, pcm: np.ndarray) -> None:
        self.rapido.prime(pcm)
        self.preciso.prime(pcm)

    def feed(self, pcm: np.ndarray) -> str | None:
        self.preciso.feed(pcm)          # só acumula
        return self.rapido.feed(pcm)    # parcial vem do modelo rápido

    def finish(self) -> str:
        final = self.preciso.finish()
        if final.strip():
            return final
        # se o preciso não devolveu nada, melhor o texto do rápido que silêncio
        alternativo = self.rapido.finish()
        if alternativo.strip():
            log.info("final do whisper veio vazio; usando o do modelo rápido")
        return alternativo


class HibridoStt(SttEngine):
    def __init__(self):
        from .base import factory
        self.rapido = factory("nemotron")
        self.preciso = factory("whisper")

    async def load(self):
        # SEQUENCIAL de propósito: os dois importam transformers e, carregando
        # em paralelo (threads diferentes), o import do Python quebra no meio
        # com "cannot import name 'AutoModel' from 'transformers'".
        await self.rapido.load()
        await self.preciso.load()

    def new_stream(self) -> SttStream:
        return HibridoStream(self.rapido.new_stream(), self.preciso.new_stream(), self)
