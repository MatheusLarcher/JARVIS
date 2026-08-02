"""Guarda o que aconteceu em cada interação — inclusive o áudio.

Serve pra três coisas:
  1. descobrir onde o JARVIS erra com a SUA voz (e não com áudio sintético);
  2. virar o material de treino do modelo pequeno mais pra frente;
  3. alimentar o observador, que analisa os casos problemáticos.

O áudio fica em server/data/gravacoes/<data>/<hora>.wav e o resto no SQLite.
"""
import logging
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from ..config import DATA_DIR, config

log = logging.getLogger("jarvis.registro")

PASTA = DATA_DIR / "gravacoes"
SAMPLE_RATE = 16000


def ativo() -> bool:
    return bool(config.settings.get("registro", {}).get("ativo", True))


def _limite_dias() -> int:
    return int(config.settings.get("registro", {}).get("guardar_dias", 30))


def salvar_audio(pcm: np.ndarray, session_id: str) -> str | None:
    """Grava a fala em WAV e devolve o caminho relativo."""
    if not ativo() or pcm is None or len(pcm) == 0:
        return None
    try:
        agora = datetime.now()
        pasta = PASTA / agora.strftime("%Y-%m-%d")
        pasta.mkdir(parents=True, exist_ok=True)
        nome = f"{agora.strftime('%H%M%S')}_{session_id[:6]}.wav"
        caminho = pasta / nome
        with wave.open(str(caminho), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm.astype(np.int16).tobytes())
        return str(caminho.relative_to(DATA_DIR)).replace("\\", "/")
    except Exception:
        log.exception("não consegui gravar o áudio")
        return None


def limpar_antigas() -> float:
    """Apaga gravações mais velhas que o limite. Devolve o corte (timestamp).

    Quem chama usa o corte pra limpar também as linhas do banco — senão a
    tabela cresce pra sempre e sobram registros apontando pra WAV que não
    existe mais.
    """
    limite = time.time() - _limite_dias() * 86400
    if not PASTA.exists():
        return limite
    apagadas = 0
    for dia in PASTA.iterdir():
        if not dia.is_dir():
            continue
        for arquivo in dia.glob("*.wav"):
            try:
                if arquivo.stat().st_mtime < limite:
                    arquivo.unlink()
                    apagadas += 1
            except OSError:
                pass
        # pasta do dia vazia some junto (rmdir FORA do except: um erro aqui
        # dentro escapava e abortava a limpeza dos dias seguintes)
        vazia = False
        try:
            next(dia.iterdir())
        except StopIteration:
            vazia = True
        except OSError:
            pass
        if vazia:
            try:
                dia.rmdir()
            except OSError:
                pass
    if apagadas:
        log.info("limpei %d gravações antigas", apagadas)
    return limite


class Registro:
    """Uma interação sendo montada, do wake até a resposta."""

    def __init__(self, device_id: str, session_id: str):
        self.device_id = device_id
        self.session_id = session_id
        self.transcricao = ""
        self.audio_path: str | None = None
        self.rota: dict = {}          # o que o roteador decidiu
        self.agente = ""
        self.resposta = ""
        self.erro: str | None = None
        self.metricas: dict = {}
