"""Nemotron 3.5 ASR streaming 0.6B via NeMo.

Estratégia MVP: transcrição incremental — a cada ~0.8s re-transcreve o buffer da
elocução (rápido na GPU pra falas curtas) e emite parcial; no fim, transcrição final.
A troca pro cache-aware streaming nativo (att_context_size) fica atrás desta mesma
interface quando validada.
"""
import asyncio
import logging
import threading
import time

import numpy as np

from ..config import config
from .base import SttEngine, SttStream

log = logging.getLogger("jarvis.stt")

# parcial rápido: é ele que faz o reator acender ao ouvir "Jarvis"
PARTIAL_INTERVAL_S = 0.45


class NemotronStream(SttStream):
    def __init__(self, engine: "NemotronStt"):
        self.engine = engine
        self.buf: list[np.ndarray] = []
        self._last_partial_t = 0.0

    def _audio(self) -> np.ndarray:
        pcm = np.concatenate(self.buf) if self.buf else np.zeros(0, dtype=np.int16)
        return pcm.astype(np.float32) / 32768.0

    def prime(self, pcm: np.ndarray) -> None:
        """Só guarda — transcrever aqui bloquearia o event loop."""
        self.buf.append(pcm)

    def feed(self, pcm: np.ndarray) -> str | None:
        self.buf.append(pcm)
        now = time.monotonic()
        # 4800 amostras = 300ms: já dá pra reconhecer a palavra-chave
        if now - self._last_partial_t >= PARTIAL_INTERVAL_S and sum(len(b) for b in self.buf) > 4800:
            self._last_partial_t = now
            return self.engine.transcribe(self._audio())
        return None

    def finish(self) -> str:
        if not self.buf:
            return ""
        return self.engine.transcribe(self._audio()) or ""


class NemotronStt(SttEngine):
    def __init__(self):
        self.model = None
        self.lang = config.settings["stt"].get("language", "pt-BR")
        # o modelo é único e compartilhado por todos os dispositivos, mas NÃO é
        # thread-safe: duas transcrições ao mesmo tempo saem vazias/corrompidas
        self._infer_lock = threading.Lock()

    async def load(self):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._load_sync)

    def _load_sync(self):
        import nemo.collections.asr as nemo_asr
        import torch
        name = config.settings["stt"]["model"]
        log.info("carregando %s ...", name)
        t0 = time.monotonic()
        self.model = nemo_asr.models.ASRModel.from_pretrained(model_name=name)
        if torch.cuda.is_available() and config.settings["stt"].get("device") == "cuda":
            self.model = self.model.cuda()
        self.model.eval()
        log.info("STT pronto em %.1fs", time.monotonic() - t0)

    def transcribe(self, audio_f32: np.ndarray) -> str | None:
        if self.model is None or len(audio_f32) == 0:
            return None
        try:
            kwargs = {"verbose": False}
            with self._infer_lock:
                try:
                    out = self.model.transcribe([audio_f32], target_lang=self.lang, **kwargs)
                except TypeError:
                    out = self.model.transcribe([audio_f32], **kwargs)
            if not out:
                return None
            first = out[0]
            text = getattr(first, "text", first if isinstance(first, str) else str(first))
            # remove tags de idioma do modelo, ex.: "<pt-PT>"
            import re
            return re.sub(r"<[a-z]{2}-[A-Z]{2}>", "", text).strip()
        except Exception:
            log.exception("erro transcrevendo")
            return None

    def new_stream(self) -> SttStream:
        return NemotronStream(self)
