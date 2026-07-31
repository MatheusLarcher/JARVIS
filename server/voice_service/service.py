"""Serviço de TTS com voz clonada (Chatterbox multilíngue) — processo separado.

Roda no env `jarvis-tts` (torch cu128 próprio) pra não conflitar com o NeMo do servidor.
O servidor JARVIS chama via HTTP e continua cacheando o resultado como qualquer TTS.

Uso: python server/voice_service/service.py     (porta 8041)
POST /tts  {"text": "...", "language": "pt", "exaggeration": 0.5, "cfg_weight": 0.5}
  → audio/wav
GET  /health
"""
import io
import logging
import os
import sys
import threading
import time
from pathlib import Path

import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
REF_WAV = ROOT / "server" / "data" / "voice" / "jarvis_ref.wav"
PORT = int(os.environ.get("JARVIS_TTS_PORT", "8041"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s voice | %(message)s")
log = logging.getLogger("voice")

app = FastAPI(title="JARVIS Voice")
_model = None
_lock = threading.Lock()


class TtsRequest(BaseModel):
    text: str
    language: str = "pt"
    exaggeration: float = 0.5
    # cfg_weight baixo demais quebra a geração no Chatterbox — manter >= 0.3
    cfg_weight: float = 0.5
    temperature: float = 0.7


def load_model():
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is None:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            device = "cuda" if torch.cuda.is_available() else "cpu"
            log.info("carregando Chatterbox multilíngue em %s ...", device)
            t0 = time.monotonic()
            _model = ChatterboxMultilingualTTS.from_pretrained(device=device)
            log.info("modelo pronto em %.1fs", time.monotonic() - t0)
    return _model


@app.get("/health")
def health():
    return {"ok": True, "loaded": _model is not None,
            "ref": REF_WAV.exists(), "cuda": torch.cuda.is_available()}


@app.post("/tts")
def tts(req: TtsRequest):
    if not REF_WAV.exists():
        return JSONResponse({"error": "referência de voz ausente"}, status_code=503)
    text = req.text.strip()
    if not text:
        return JSONResponse({"error": "texto vazio"}, status_code=400)
    model = load_model()
    t0 = time.monotonic()
    with _lock:                      # o modelo não é thread-safe
        wav = model.generate(
            text,
            language_id=req.language,
            audio_prompt_path=str(REF_WAV),
            exaggeration=req.exaggeration,
            cfg_weight=req.cfg_weight,
            temperature=req.temperature,
        )
    buf = io.BytesIO()
    sf.write(buf, wav.squeeze(0).cpu().numpy(), model.sr, format="WAV", subtype="PCM_16")
    dur = wav.shape[-1] / model.sr
    log.info("gerado %.1fs de áudio em %.1fs | %r", dur, time.monotonic() - t0, text[:60])
    return Response(content=buf.getvalue(), media_type="audio/wav")


if __name__ == "__main__":
    if "--preload" in sys.argv:
        load_model()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
