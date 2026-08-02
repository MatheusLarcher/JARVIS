"""Montagem do app FastAPI do JARVIS."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .audio.pipeline import Shared
from .config import ROOT, config
from .gateway import rest, ws
from .home_assistant.client import ha
from .memory.db import store

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s | %(message)s")
log = logging.getLogger("jarvis")


async def _limpar_registros_antigos():
    """Gravações e linhas do registro além do prazo (registro.guardar_dias)."""
    try:
        from .memory.registro import limpar_antigas
        corte = await asyncio.to_thread(limpar_antigas)
        linhas = await store.limpar_registros(corte)
        if linhas:
            log.info("removi %d registros antigos do banco", linhas)
    except Exception:
        log.exception("falha limpando registros antigos")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.open()
    await ha.start()
    await Shared.load()
    # deixa o agente pronto antes da primeira pergunta (economiza ~4,5s nela)
    from .agents.agent import aquecer as aquecer_agente
    asyncio.create_task(aquecer_agente())

    # gravações velhas somem sozinhas (registro.guardar_dias), com as linhas junto
    asyncio.create_task(_limpar_registros_antigos())

    warm_task = None
    if config.settings["tts"].get("cache_warmer"):
        from .tts.warmer import run as warm_run
        warm_task = asyncio.create_task(warm_run())
    log.info("JARVIS online.")
    yield
    if warm_task:
        warm_task.cancel()
    await ha.stop()
    await store.close()


app = FastAPI(title="JARVIS", lifespan=lifespan)
app.include_router(ws.router)
app.include_router(rest.router)

# web buildada (apps/web/dist) servida na raiz quando existir
_web_dist = ROOT / "apps" / "web" / "dist"
if _web_dist.is_dir():
    app.mount("/", StaticFiles(directory=_web_dist, html=True), name="web")
