"""Aquecedor de cache: mantém as frases previsíveis já geradas.

A voz clonada é lenta pra gerar (RTF ~4), então tudo que dá pra antecipar é
gerado antes de alguém pedir — pedir a hora ou a temperatura fica instantâneo.
As frases têm que ser IDÊNTICAS às das skills, senão o hash do cache não bate.
"""
import asyncio
import logging
from datetime import datetime, timedelta

from .. import activity
from ..home_assistant.client import ha
from .engine import tts

log = logging.getLogger("jarvis.tts.warmer")

INTERVAL_S = 30


def time_phrase(now: datetime) -> str:
    """Mesmo texto do InfoSkill.info_time."""
    if now.minute == 0:
        return f"São {now.hour} horas em ponto."
    return f"São {now.hour} horas e {now.minute:02d} minutos."


def temperature_phrase(temp: float) -> str:
    """Mesmo texto do InfoSkill.info_temperature."""
    return f"A temperatura ambiente é de {temp:.0f} graus."


async def _warm(text: str):
    if not tts.is_cached(text):
        log.info("pré-gerando: %s", text)
        await tts.get_or_synthesize(text)


async def run():
    """Loop de fundo; começa pelo minuto atual e vai um minuto à frente."""
    while True:
        try:
            if activity.is_busy():      # interação em andamento tem a GPU
                await asyncio.sleep(1)
                continue
            now = datetime.now()
            await _warm(time_phrase(now))
            await _warm(time_phrase(now + timedelta(minutes=1)))
            temp = await ha.temperature()
            if temp is not None:
                await _warm(temperature_phrase(temp))
        except Exception:
            log.exception("erro no aquecedor de cache")
        await asyncio.sleep(INTERVAL_S)
