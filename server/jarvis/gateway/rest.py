"""REST: serve áudios (biblioteca + cache TTS), status e métricas."""
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import ROOT, config
from ..memory.db import store

log = logging.getLogger("jarvis.rest")
router = APIRouter()

_LIB = ROOT / config.settings["tts"]["library_dir"]
_TTS = ROOT / config.settings["tts"]["cache_dir"]


@router.get("/audio/library/{intent}/{name}")
async def audio_library(intent: str, name: str):
    path = (_LIB / intent / name).resolve()
    if not str(path).startswith(str(_LIB.resolve())) or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


@router.get("/audio/tts/{name}")
async def audio_tts(name: str):
    path = (_TTS / name).resolve()
    if not str(path).startswith(str(_TTS.resolve())) or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


@router.get("/api/status")
async def status():
    from .ws import connections
    return {"ok": True, "devices_online": list(connections.keys())}


@router.get("/api/audio/debug")
async def audio_debug():
    """O áudio de cada dispositivo está chegando? Com que intensidade?

    rms_maximo ~0        -> microfone mudo (headset na base, mic desligado)
    rms_maximo > 0.01    -> chega som
    vad_maximo > 0.5     -> o servidor reconhece como FALA
    """
    from .ws import pipelines
    return {dev: p.stats for dev, p in pipelines.items()}


@router.get("/api/metrics/recent")
async def recent_metrics(limit: int = 20):
    cur = await store._db.execute(
        "SELECT ts, device_id, transcript, intent, handler, metrics_json "
        "FROM interactions ORDER BY id DESC LIMIT ?", (limit,))
    rows = await cur.fetchall()
    return [{"ts": r[0], "device_id": r[1], "transcript": r[2], "intent": r[3],
             "handler": r[4], "metrics": r[5]} for r in rows]
