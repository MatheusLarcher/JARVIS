"""Pipeline de áudio por dispositivo: wake word → VAD → STT streaming.

Recebe frames PCM int16 16kHz do WebSocket e dispara callbacks async:
  on_wake(), on_partial(texto), on_final(texto), on_timeout()
"""
import asyncio
import logging
import time
from enum import Enum

import numpy as np

from ..config import config

log = logging.getLogger("jarvis.audio")

SAMPLE_RATE = 16000
WAKE_FRAME = 1280      # 80ms — exigido pelo openWakeWord
VAD_FRAME = 512        # exigido pelo Silero VAD em 16kHz


class Shared:
    """Recursos carregados uma única vez. STT é stateless por stream e pode ser
    compartilhado; wake word e VAD são STATEFUL e ficam um por conexão."""

    stt_engine = None

    @classmethod
    async def load(cls):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, cls._prefetch)
        from ..stt.base import factory
        cls.stt_engine = factory(config.settings["stt"]["engine"])
        await cls.stt_engine.load()

    @classmethod
    def _prefetch(cls):
        import openwakeword
        openwakeword.utils.download_models(["hey_jarvis"])
        from silero_vad import load_silero_vad
        load_silero_vad()  # aquece o cache do torch.hub
        log.info("modelos de wake word + VAD disponíveis")

    @staticmethod
    def new_wake_model():
        from openwakeword.model import Model
        return Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")

    @staticmethod
    def new_vad_model():
        from silero_vad import load_silero_vad
        return load_silero_vad()


class Phase(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    BUSY = "busy"          # processando comando; áudio é ignorado


class AudioPipeline:
    def __init__(self, device_id: str, on_wake, on_partial, on_final, on_timeout):
        self.device_id = device_id
        self.on_wake, self.on_partial, self.on_final, self.on_timeout = \
            on_wake, on_partial, on_final, on_timeout
        self.phase = Phase.IDLE
        self._wake_buf = np.zeros(0, dtype=np.int16)
        self._vad_buf = np.zeros(0, dtype=np.int16)
        self._stt_stream = None
        self._last_wake_t = 0.0
        self._listen_start = 0.0
        self._speech_seen = False
        self._silence_start: float | None = None
        cfg = config.settings
        self._wake_threshold = cfg["wake_word"]["threshold"]
        self._refractory = cfg["wake_word"]["refractory_s"]
        self._end_silence = cfg["vad"]["end_silence_s"]
        self._max_utt = cfg["vad"]["max_utterance_s"]
        self._vad_threshold = cfg["vad"]["threshold"]
        self._lock = asyncio.Lock()
        self.wake_model = None
        self.vad_model = None

    async def init(self):
        """Cria os modelos stateful desta conexão (fora do event loop)."""
        loop = asyncio.get_running_loop()
        self.wake_model, self.vad_model = await loop.run_in_executor(
            None, lambda: (Shared.new_wake_model(), Shared.new_vad_model()))

    async def feed(self, pcm_bytes: bytes):
        pcm = np.frombuffer(pcm_bytes, dtype=np.int16)
        async with self._lock:
            if self.phase == Phase.IDLE:
                await self._feed_wake(pcm)
            elif self.phase == Phase.LISTENING:
                await self._feed_listen(pcm)
            # BUSY: descarta

    async def start_listening(self, from_wake: bool = False):
        """Entra em captura (chamado pelo wake ou por push-to-talk do watch)."""
        self.phase = Phase.LISTENING
        self._stt_stream = Shared.stt_engine.new_stream()
        self._listen_start = time.monotonic()
        self._speech_seen = False
        self._silence_start = None
        self._vad_buf = np.zeros(0, dtype=np.int16)
        if self.wake_model:
            self.wake_model.reset()

    def set_busy(self):
        self.phase = Phase.BUSY
        self._stt_stream = None

    def set_idle(self):
        self.phase = Phase.IDLE
        self._stt_stream = None
        self._wake_buf = np.zeros(0, dtype=np.int16)

    async def _feed_wake(self, pcm: np.ndarray):
        if self.wake_model is None:
            return
        self._wake_buf = np.concatenate([self._wake_buf, pcm])
        while len(self._wake_buf) >= WAKE_FRAME:
            frame, self._wake_buf = self._wake_buf[:WAKE_FRAME], self._wake_buf[WAKE_FRAME:]
            scores = self.wake_model.predict(frame)
            score = max(scores.values()) if scores else 0.0
            now = time.monotonic()
            if score >= self._wake_threshold and now - self._last_wake_t > self._refractory:
                self._last_wake_t = now
                log.info("[%s] wake word (score=%.2f)", self.device_id, score)
                await self.start_listening(from_wake=True)
                await self.on_wake()
                return

    async def _feed_listen(self, pcm: np.ndarray):
        import torch
        loop = asyncio.get_running_loop()
        now = time.monotonic()

        # VAD em janelas de 512 amostras
        self._vad_buf = np.concatenate([self._vad_buf, pcm])
        speech_prob = 0.0
        while len(self._vad_buf) >= VAD_FRAME:
            win, self._vad_buf = self._vad_buf[:VAD_FRAME], self._vad_buf[VAD_FRAME:]
            t = torch.from_numpy(win.astype(np.float32) / 32768.0)
            speech_prob = max(speech_prob, float(self.vad_model(t, SAMPLE_RATE).item()))

        if speech_prob >= self._vad_threshold:
            self._speech_seen = True
            self._silence_start = None
        elif self._speech_seen and self._silence_start is None:
            self._silence_start = now

        # STT (parciais rodam fora do event loop)
        partial = await loop.run_in_executor(None, self._stt_stream.feed, pcm)
        if partial:
            await self.on_partial(partial)

        ended_by_silence = (self._silence_start is not None
                            and now - self._silence_start >= self._end_silence)
        timed_out = now - self._listen_start >= self._max_utt
        no_speech_timeout = (not self._speech_seen
                             and now - self._listen_start >= min(5.0, self._max_utt))

        if ended_by_silence or timed_out:
            stream = self._stt_stream
            self.set_busy()
            final = await loop.run_in_executor(None, stream.finish)
            log.info("[%s] final: %r", self.device_id, final)
            if final.strip():
                await self.on_final(final.strip())
            else:
                await self.on_timeout()
        elif no_speech_timeout:
            self.set_idle()
            await self.on_timeout()
