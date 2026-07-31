"""Sinal global de "tem alguém falando com o JARVIS agora".

Serve pra tarefas de fundo (ex.: aquecedor de cache do TTS) saírem da frente:
STT e TTS dividem a mesma GPU e a interação sempre tem prioridade.
"""
import time

_active = 0
_last_end = 0.0
COOLDOWN_S = 3.0


def begin():
    global _active
    _active += 1


def end():
    global _active, _last_end
    _active = max(0, _active - 1)
    _last_end = time.monotonic()


def is_busy() -> bool:
    return _active > 0 or (time.monotonic() - _last_end) < COOLDOWN_S
