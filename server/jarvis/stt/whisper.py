"""Whisper (faster-whisper) — transcrição final de alta qualidade.

Não é streaming: precisa da fala inteira. Por isso ele é usado no FIM da
elocução, quando a precisão importa; as parciais ficam com um modelo rápido.

Medido neste projeto (RTX 5050, large-v3-turbo, float16):
  frase curta ~0,7s | WER 0.000 mesmo com ruído/eco (o Nemotron erra ~6%)
"""
import asyncio
import logging
import threading
import time

import numpy as np

from ..config import config
from .base import SttEngine, SttStream

log = logging.getLogger("jarvis.stt")


def _hotwords_padrao() -> str:
    """Palavras que o modelo precisa 'esperar' ouvir — o nome do assistente e o
    vocabulário da casa. Sem isso o STT troca 'Jarvis' por 'Já Luiz'/'Jairus'."""
    palavras = [config.settings["wake_word"].get("keyword", "jarvis").capitalize()]
    palavras += list((config.house.get("house") or {}).keys())          # cômodos
    palavras += ["luz", "luzes", "temperatura", "ligar", "desligar", "acender",
                 "apagar", "navegador"]
    return " ".join(dict.fromkeys(palavras))


class WhisperStream(SttStream):
    def __init__(self, engine: "WhisperStt"):
        self.engine = engine
        self.buf: list[np.ndarray] = []
        self._ultima_parcial = 0.0

    def prime(self, pcm: np.ndarray) -> None:
        self.buf.append(pcm)

    def feed(self, pcm: np.ndarray) -> str | None:
        self.buf.append(pcm)
        if not self.engine.parciais:
            return None
        # o small transcreve em ~0,1s, então dá pra re-transcrever o trecho
        # em andamento e ir dando parciais (é o que acende o reator cedo)
        agora = time.monotonic()
        amostras = sum(len(b) for b in self.buf)
        if (agora - self._ultima_parcial >= self.engine.intervalo_parcial
                and amostras > 4800):
            self._ultima_parcial = agora
            return self.engine.transcribe(self._audio())
        return None

    def _audio(self) -> np.ndarray:
        pcm = np.concatenate(self.buf) if self.buf else np.zeros(0, dtype=np.int16)
        return pcm.astype(np.float32) / 32768.0

    def finish(self) -> str:
        return self.engine.transcribe(self._audio()) or ""


class WhisperStt(SttEngine):
    def __init__(self):
        cfg = config.settings["stt"]
        self.model_name = cfg.get("whisper_model", "large-v3-turbo")
        self.device = cfg.get("device", "cuda")
        self.compute_type = cfg.get("whisper_compute_type", "float16")
        self.lang = (cfg.get("language", "pt-BR") or "pt").split("-")[0]
        self.beam_size = int(cfg.get("whisper_beam_size", 1))
        # com o modelo pequeno dá pra ele mesmo gerar as parciais
        self.parciais = bool(cfg.get("whisper_parciais", False))
        self.intervalo_parcial = float(cfg.get("whisper_intervalo_parcial", 0.45))
        # vocabulário da casa: nome do assistente, cômodos e comandos comuns
        self.hotwords = cfg.get("hotwords") or _hotwords_padrao()
        self.contexto = cfg.get("initial_prompt") or (
            "Conversa com o assistente de voz Jarvis. "
            "Exemplos: Jarvis, liga a luz da sala. Jarvis, desliga a luz do quarto. "
            "Jarvis, que horas são? Jarvis, abre o navegador.")
        self.model = None
        self._infer_lock = threading.Lock()

    async def load(self):
        await asyncio.get_running_loop().run_in_executor(None, self._load_sync)

    def _load_sync(self):
        from faster_whisper import WhisperModel
        log.info("carregando whisper %s (%s/%s) ...", self.model_name,
                 self.device, self.compute_type)
        t0 = time.monotonic()
        try:
            self.model = WhisperModel(self.model_name, device=self.device,
                                      compute_type=self.compute_type)
        except Exception:
            log.exception("whisper falhou na GPU; caindo pra CPU")
            self.model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
        log.info("whisper pronto em %.1fs", time.monotonic() - t0)

    def transcribe(self, audio_f32: np.ndarray) -> str | None:
        if self.model is None or len(audio_f32) == 0:
            return None
        try:
            with self._infer_lock:
                segs, _ = self.model.transcribe(
                    audio_f32, language=self.lang, beam_size=self.beam_size,
                    vad_filter=False, condition_on_previous_text=False,
                    # sem isto o modelo não conhece "Jarvis" e escreve
                    # "Já Luiz", "Jairus", "Já vi"... quebrando o wake word
                    initial_prompt=self.contexto,
                    hotwords=self.hotwords)
                return " ".join(s.text for s in segs).strip()
        except Exception:
            log.exception("erro transcrevendo (whisper)")
            return None

    def new_stream(self) -> SttStream:
        return WhisperStream(self)
