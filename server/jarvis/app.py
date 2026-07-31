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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.open()
    await ha.start()
    await Shared.load()
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
