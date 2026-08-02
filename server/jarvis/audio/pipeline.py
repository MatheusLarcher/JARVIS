"""Pipeline de áudio por dispositivo: VAD → STT streaming → palavra-chave → comando.

Como funciona (modo `stt`, o padrão):

  IDLE      guarda um pre-roll curto e espera o VAD acusar fala.
  SCANNING  transcreve a fala desde o começo (graças ao pre-roll) procurando
            "jarvis" nas parciais. Assim que aparece, o reator já acende.
            No fim da fala, o que veio junto com o nome VIRA O COMANDO —
            é o que permite dizer "Jarvis, liga a luz" numa frase só.
            Se a fala não tinha o nome, é descartada em silêncio.
  COMMAND   quando a pessoa só chamou ("Jarvis"), toca o "Sim?" e ouve a
            próxima fala inteira como comando (sem exigir o nome de novo).
  BUSY      executando; áudio ignorado.

O openWakeWord continua rodando em paralelo como atalho instantâneo pra
"hey jarvis" — o que disparar primeiro vence.

Callbacks: on_wake(), on_ack(), on_partial(txt), on_final(txt), on_timeout()
"""
import asyncio
import logging
import time
from enum import Enum

import numpy as np

from ..config import config
from .wakeword import matcher

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
        openwakeword.utils.download_models([config.settings["wake_word"]["openwakeword_model"]])
        from silero_vad import load_silero_vad
        load_silero_vad()  # aquece o cache do torch.hub
        log.info("modelos de wake word + VAD disponíveis")

    @staticmethod
    def new_wake_model():
        from openwakeword.model import Model
        return Model(wakeword_models=[config.settings["wake_word"]["openwakeword_model"]],
                     inference_framework="onnx")

    @staticmethod
    def new_vad_model():
        from silero_vad import load_silero_vad
        return load_silero_vad()


class Phase(str, Enum):
    IDLE = "idle"
    SCANNING = "scanning"    # ouvindo, ainda não sei se falaram comigo
    COMMAND = "command"      # já chamou; esta fala é o comando
    BUSY = "busy"


class AudioPipeline:
    def __init__(self, device_id, on_wake, on_ack, on_partial, on_final, on_timeout):
        self.device_id = device_id
        self.on_wake, self.on_ack = on_wake, on_ack
        self.on_partial, self.on_final, self.on_timeout = on_partial, on_final, on_timeout

        cfg = config.settings
        self.mode = cfg["wake_word"].get("engine", "stt")
        self._wake_threshold = cfg["wake_word"]["threshold"]
        self._refractory = cfg["wake_word"]["refractory_s"]
        self._preroll_n = int(SAMPLE_RATE * cfg["wake_word"].get("preroll_s", 1.0))
        self._followup_s = cfg["wake_word"].get("followup_s", 6.0)
        self._end_silence = cfg["vad"]["end_silence_s"]
        self._max_utt = cfg["vad"]["max_utterance_s"]
        self._vad_threshold = cfg["vad"]["threshold"]
        # com o registro desligado nem guardamos o áudio (config/settings.yml)
        self._gravando = bool(cfg.get("registro", {}).get("ativo", True))

        self.phase = Phase.IDLE
        self.wake_model = None
        self.vad_model = None
        self._lock = asyncio.Lock()

        self._preroll = np.zeros(0, dtype=np.int16)
        self._wake_buf = np.zeros(0, dtype=np.int16)
        self._vad_buf = np.zeros(0, dtype=np.int16)
        # áudio bruto da fala atual; vira gravação pro registro (memory/registro.py).
        # Lista de pedaços, não um array crescendo: concatenar a cada frame de
        # 80ms copiaria o buffer inteiro ~150 vezes por fala, dentro do loop.
        self._pcm_fala: list[np.ndarray] = []
        self._amostras_fala = 0
        self.audio_da_fala: np.ndarray | None = None
        self._stt_stream = None
        self._parcial_task = None                       # transcrição em andamento
        self._pcm_pendente = np.zeros(0, dtype=np.int16)  # áudio que chegou durante ela
        self._last_wake_t = 0.0
        self._speech_start = 0.0
        self._silence_start: float | None = None
        self._speech_seen = False
        self._woke_in_this_utterance = False
        self._await_until = 0.0
        self._speech_frames = 0
        # ~240ms de fala contínua antes de acionar o STT
        self._min_speech_frames = max(1, int(cfg["vad"].get("min_speech_ms", 240) / 80))
        self._parcial_task = None
        self._pcm_pendente = np.zeros(0, dtype=np.int16)

        # diagnóstico: dá pra ver se o áudio do dispositivo está chegando e com
        # que intensidade — é a primeira coisa a checar quando "ele não me ouve"
        self.stats = {"frames": 0, "rms_atual": 0.0, "rms_maximo": 0.0,
                      "vad_maximo": 0.0, "ultima_fala_ha_s": None, "fase": "idle"}
        self._last_speech_t = 0.0

    async def init(self):
        """Cria os modelos stateful desta conexão (fora do event loop)."""
        loop = asyncio.get_running_loop()
        self.wake_model, self.vad_model = await loop.run_in_executor(
            None, lambda: (Shared.new_wake_model(), Shared.new_vad_model()))

    # ------------------------------------------------------------------ entrada
    async def feed(self, pcm_bytes: bytes):
        pcm = np.frombuffer(pcm_bytes, dtype=np.int16)
        rms = float(np.sqrt(np.mean(pcm.astype(np.float32) ** 2))) / 32768.0
        s = self.stats
        s["frames"] += 1
        s["rms_atual"] = round(rms, 5)
        s["rms_maximo"] = round(max(s["rms_maximo"], rms), 5)
        s["fase"] = self.phase.value
        s["ultima_fala_ha_s"] = (round(time.monotonic() - self._last_speech_t, 1)
                                 if self._last_speech_t else None)
        async with self._lock:
            if self.phase == Phase.BUSY:
                return
            if self.phase == Phase.IDLE:
                await self._feed_idle(pcm)
            else:
                await self._feed_utterance(pcm)

    def _vad_prob(self, pcm: np.ndarray) -> float:
        import torch
        self._vad_buf = np.concatenate([self._vad_buf, pcm])
        prob = 0.0
        while len(self._vad_buf) >= VAD_FRAME:
            win, self._vad_buf = self._vad_buf[:VAD_FRAME], self._vad_buf[VAD_FRAME:]
            t = torch.from_numpy(win.astype(np.float32) / 32768.0)
            prob = max(prob, float(self.vad_model(t, SAMPLE_RATE).item()))
        self.stats["vad_maximo"] = round(max(self.stats["vad_maximo"], prob), 3)
        if prob >= self._vad_threshold:
            self._last_speech_t = time.monotonic()
        return prob

    async def _feed_idle(self, pcm: np.ndarray):
        now = time.monotonic()

        # atalho: openWakeWord ("hey jarvis") responde na hora
        if self.wake_model is not None:
            self._wake_buf = np.concatenate([self._wake_buf, pcm])
            while len(self._wake_buf) >= WAKE_FRAME:
                frame, self._wake_buf = self._wake_buf[:WAKE_FRAME], self._wake_buf[WAKE_FRAME:]
                scores = self.wake_model.predict(frame)
                if scores and max(scores.values()) >= self._wake_threshold \
                        and now - self._last_wake_t > self._refractory:
                    self._last_wake_t = now
                    log.info("[%s] wake word (openWakeWord)", self.device_id)
                    await self.on_wake()
                    await self.on_ack()
                    self._begin_utterance(Phase.COMMAND, preroll=False)
                    return

        # pre-roll: guarda o áudio recente pra não perder o começo da frase
        self._preroll = np.concatenate([self._preroll, pcm])[-self._preroll_n:]

        if self.mode != "stt":
            return
        # exige fala SUSTENTADA: um ruído isolado não vale a pena transcrever
        if self._vad_prob(pcm) >= self._vad_threshold:
            self._speech_frames += 1
        else:
            self._speech_frames = 0
        if self._speech_frames >= self._min_speech_frames:
            log.debug("[%s] fala detectada; transcrevendo pra ver se é comigo", self.device_id)
            self._begin_utterance(Phase.SCANNING, preroll=True)

    def _begin_utterance(self, phase: Phase, preroll: bool):
        self.phase = phase
        self._stt_stream = Shared.stt_engine.new_stream()
        self._pcm_fala = []
        self._amostras_fala = 0
        if preroll and len(self._preroll):
            self._stt_stream.prime(self._preroll)   # sem transcrever: estamos no event loop
            if self._gravando:
                self._pcm_fala = [self._preroll.copy()]   # a gravação já começa com a fala
                self._amostras_fala = len(self._preroll)
        self._preroll = np.zeros(0, dtype=np.int16)
        self._wake_buf = np.zeros(0, dtype=np.int16)
        self._vad_buf = np.zeros(0, dtype=np.int16)
        self._speech_start = time.monotonic()
        self._silence_start = None
        # em SCANNING o VAD já acusou fala; em COMMAND ainda vamos esperar a pessoa falar
        self._speech_seen = phase == Phase.SCANNING
        self._woke_in_this_utterance = False
        self._await_until = time.monotonic() + self._followup_s
        self._parcial_task = None
        self._pcm_pendente = np.zeros(0, dtype=np.int16)
        if self.wake_model:
            self.wake_model.reset()

    async def _feed_utterance(self, pcm: np.ndarray):
        loop = asyncio.get_running_loop()
        now = time.monotonic()

        # guarda o áudio da fala (teto = a duração máxima permitida, sem surpresa
        # de memória num servidor que fica ligado o dia todo)
        if self._gravando:
            self._pcm_fala.append(pcm)
            self._amostras_fala += len(pcm)
            limite = int(SAMPLE_RATE * (self._max_utt + 2))
            while self._amostras_fala > limite and len(self._pcm_fala) > 1:
                self._amostras_fala -= len(self._pcm_fala.pop(0))

        speaking = self._vad_prob(pcm) >= self._vad_threshold
        if speaking:
            self._speech_seen = True
            self._silence_start = None
            self._await_until = now + self._followup_s
        elif self._speech_seen and self._silence_start is None:
            self._silence_start = now

        # A transcrição parcial NÃO pode bloquear: enquanto ela roda, os frames
        # de áudio se acumulam e o pipeline fica para trás do tempo real (isso
        # fazia o JARVIS "desistir de esperar o comando" no meio da fala).
        partial = await self._parcial_sem_travar(pcm)
        if partial:
            if self.phase == Phase.SCANNING:
                # acende o reator assim que o nome aparece, sem esperar a frase acabar
                hit, _ = matcher.match(partial)
                if hit and not self._woke_in_this_utterance:
                    self._woke_in_this_utterance = True
                    self._last_wake_t = now
                    log.info("[%s] chamou: %r", self.device_id, partial)
                    await self.on_wake()
                if self._woke_in_this_utterance:
                    await self.on_partial(partial)
            else:
                await self.on_partial(partial)

        # o silêncio só encerra depois que a pessoa realmente falou — senão a
        # pausa entre o "Jarvis" e o comando cortaria a captura na hora
        silence = (self._speech_seen and self._silence_start is not None
                   and now - self._silence_start >= self._end_silence)
        too_long = self._speech_seen and now - self._speech_start >= self._max_utt
        gave_up = self.phase == Phase.COMMAND and now >= self._await_until

        if silence or too_long:
            await self._end_utterance()
        elif gave_up:
            log.info("[%s] desisti de esperar o comando (%.1fs sem fala)",
                     self.device_id, self._followup_s)
            self._reset_idle()
            await self.on_timeout()

    async def _parcial_sem_travar(self, pcm: np.ndarray) -> str | None:
        """Entrega o áudio ao STT e devolve parcial só se já estiver pronta.

        O áudio é sempre acumulado na hora (barato). A transcrição roda numa
        tarefa à parte; se ainda estiver rodando, o frame seguinte não espera.
        """
        stream = self._stt_stream
        if stream is None:
            return None
        loop = asyncio.get_running_loop()

        if self._parcial_task is None or self._parcial_task.done():
            pronta = None
            if self._parcial_task is not None:
                try:
                    pronta = self._parcial_task.result()
                except Exception:
                    pronta = None
            pendente, self._pcm_pendente = self._pcm_pendente, np.zeros(0, dtype=np.int16)
            junto = np.concatenate([pendente, pcm]) if len(pendente) else pcm
            self._parcial_task = loop.run_in_executor(None, stream.feed, junto)
            return pronta
        # transcrição anterior ainda rodando: guarda o áudio e segue a vida
        self._pcm_pendente = np.concatenate([self._pcm_pendente, pcm])
        return None

    async def _end_utterance(self):
        loop = asyncio.get_running_loop()
        stream = self._stt_stream
        phase = self.phase
        self.phase = Phase.BUSY
        self._stt_stream = None
        # o que sobrou enquanto a última parcial rodava não pode se perder
        if self._parcial_task is not None:
            try:
                await self._parcial_task
            except Exception:
                pass
            self._parcial_task = None
        if len(self._pcm_pendente):
            await loop.run_in_executor(None, stream.prime, self._pcm_pendente)
            self._pcm_pendente = np.zeros(0, dtype=np.int16)

        text = (await loop.run_in_executor(None, stream.finish) or "").strip()
        log.info("[%s] fala: %r (fase=%s)", self.device_id, text, phase.value)

        if phase == Phase.COMMAND:
            if text:
                self._publicar_audio()
                await self.on_final(text)
            else:
                self._reset_idle()
                await self.on_timeout()
            return

        # SCANNING: só interessa se falaram comigo
        hit, command = matcher.match(text)
        if not hit:
            if self._woke_in_this_utterance:      # parcial enganou; volta ao repouso
                self._reset_idle()
                await self.on_timeout()
            else:
                self._reset_idle()
            return

        if not self._woke_in_this_utterance:      # nome só apareceu no texto final
            await self.on_wake()

        if command:
            self._publicar_audio()
            await self.on_final(command)          # comando veio na mesma frase
        else:
            await self.on_ack()                   # só chamou: responde e espera
            self._begin_utterance(Phase.COMMAND, preroll=False)
            log.info("[%s] chamou sem comando; ouvindo o que vem agora",
                     self.device_id)

    def _publicar_audio(self):
        """Entrega o áudio da fala pro registro — só quando ela virou pedido.

        Uma fala descartada (conversa na sala sem chamar o JARVIS) NÃO pode
        ficar guardada aqui: a interação seguinte pegaria esse áudio de outra
        pessoa e gravaria como se fosse o pedido dela.
        """
        if not self._gravando or not self._pcm_fala:
            self.audio_da_fala = None
            return
        self.audio_da_fala = np.concatenate(self._pcm_fala)
        self._pcm_fala = []
        self._amostras_fala = 0

    # ------------------------------------------------------------------ estado
    def _reset_idle(self):
        self.phase = Phase.IDLE
        self._stt_stream = None
        self._pcm_fala = []
        self._amostras_fala = 0
        self._preroll = np.zeros(0, dtype=np.int16)
        self._wake_buf = np.zeros(0, dtype=np.int16)
        self._vad_buf = np.zeros(0, dtype=np.int16)
        self._woke_in_this_utterance = False
        self._speech_frames = 0
        if self.wake_model:
            self.wake_model.reset()

    async def start_listening(self):
        """Push-to-talk: ouvir o comando direto, sem palavra-chave."""
        self._begin_utterance(Phase.COMMAND, preroll=False)

    def set_busy(self):
        self.phase = Phase.BUSY
        self._stt_stream = None

    def set_idle(self):
        self._reset_idle()
