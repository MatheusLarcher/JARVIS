"""WebSocket do Device Gateway: /ws/{device_id}?token=...

JSON (texto) pra eventos; binário = PCM int16 16kHz mono.
"""
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import activity
from ..agents import agent as adk_agent
from ..audio.pipeline import AudioPipeline
from ..config import config
from ..context.engine import context_engine
from ..home_assistant.client import ha
from ..memory.db import store
from .dialog import DialogManager

log = logging.getLogger("jarvis.ws")
router = APIRouter()

connections: dict[str, WebSocket] = {}
pipelines: dict[str, "AudioPipeline"] = {}   # pra diagnóstico de áudio


def _auth(device_id: str, token: str | None) -> bool:
    dev = config.devices.get(device_id)
    return bool(dev and token and dev["token"] == token)


@router.websocket("/ws/{device_id}")
async def ws_device(websocket: WebSocket, device_id: str, token: str | None = None):
    if not _auth(device_id, token):
        await websocket.close(code=4401)
        log.warning("conexão recusada: %s", device_id)
        return
    await websocket.accept()
    connections[device_id] = websocket
    log.info("conectado: %s", device_id)

    async def send(msg: dict):
        try:
            await websocket.send_text(json.dumps(msg, ensure_ascii=False))
        except Exception:
            pass

    def pegar_audio():
        """O PCM da última fala, uma vez só — senão gruda numa interação seguinte
        que não veio de voz (pedido digitado, por exemplo)."""
        pcm = getattr(pipeline, "audio_da_fala", None)
        if pcm is not None:
            pipeline.audio_da_fala = None
        return pcm

    dialog = DialogManager(device_id, send, obter_audio=pegar_audio)

    async def on_wake():
        activity.begin()
        # acorda a GPU agora, enquanto o comando ainda está sendo falado
        asyncio.create_task(adk_agent.despertar_gpu())
        dialog.start_interaction()
        # só acende o reator; o "Sim?" vem no ack (pode nem vir, se o comando
        # tiver sido dito na mesma frase)
        await send({"type": "wake"})
        await send({"type": "state", "state": "LISTENING"})

    async def on_ack():
        # device toca um áudio de confirmação já cacheado localmente
        await send({"type": "ack"})

    async def on_partial(text: str):
        # marca só o PRIMEIRO parcial: é a latência percebida de feedback
        if dialog.interaction and "stt_partial_ms" not in dialog.interaction.marks:
            dialog.interaction.mark("stt_partial_ms")
        await send({"type": "stt_partial", "text": text})

    async def on_final(text: str):
        try:
            await dialog.on_final(text)
        finally:
            activity.end()
        pipeline.set_idle()
        await send({"type": "state", "state": "IDLE"})

    async def on_timeout():
        activity.end()
        pipeline.set_idle()
        await dialog.on_timeout()

    pipeline = AudioPipeline(device_id, on_wake, on_ack, on_partial, on_final, on_timeout)
    await pipeline.init()
    pipelines[device_id] = pipeline

    ambient_task = asyncio.create_task(_ambient_loop(send))
    try:
        while True:
            msg = await websocket.receive()
            if msg.get("bytes") is not None:
                await pipeline.feed(msg["bytes"])
            elif msg.get("text"):
                await _handle_json(device_id, json.loads(msg["text"]), send, pipeline,
                                   dialog, on_final)
            elif msg.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        ambient_task.cancel()
        connections.pop(device_id, None)
        pipelines.pop(device_id, None)
        ctx = context_engine.get(device_id)
        if ctx:
            await store.save_device_context(device_id, ctx.snapshot())
        log.info("desconectado: %s", device_id)


async def _handle_json(device_id: str, msg: dict, send, pipeline: AudioPipeline,
                       dialog: DialogManager, on_final_texto):
    t = msg.get("type")
    if t == "hello":
        ctx = context_engine.register(device_id, msg)
        await send({"type": "hello_ok", "context": ctx.snapshot(),
                    "ack_sounds": _ack_sounds()})
        await send({"type": "state", "state": "IDLE"})
    elif t == "context":
        context_engine.update(device_id, msg)
    elif t == "mic_open":
        # push-to-talk (watch/celular): começa a ouvir sem wake word
        activity.begin()
        dialog.start_interaction()
        await pipeline.start_listening()
        await send({"type": "state", "state": "LISTENING"})
    elif t == "texto":
        # pedido escrito (testes e, no futuro, digitar em vez de falar)
        texto = (msg.get("text") or "").strip()
        if texto:
            activity.begin()
            dialog.start_interaction()
            await send({"type": "stt_final", "text": texto})
            await on_final_texto(texto)
    elif t == "mic_close":
        pipeline.set_idle()
        await send({"type": "state", "state": "IDLE"})
    elif t == "ping":
        await send({"type": "pong", "ts": msg.get("ts")})


def _ack_sounds() -> list[dict]:
    """Lista dos áudios de confirmação pro device baixar e cachear localmente."""
    from ..tts.library import library as _lib
    library = _lib
    folder = library.dir / "acknowledgement"
    if not folder.is_dir():
        return []
    # a URL leva a versão do arquivo: trocar a voz invalida o cache do aparelho
    return [{"name": f.name,
             "url": library.url_de(f, "/audio/library/acknowledgement")}
            for f in sorted(folder.iterdir()) if f.suffix in (".mp3", ".wav")]


async def _ambient_loop(send):
    """Hora + temperatura pro modo repouso do tablet, a cada 60s."""
    while True:
        try:
            temp = await ha.temperature()
            await send({"type": "ambient", "temperature_c": temp})
        except Exception:
            pass
        await asyncio.sleep(60)
