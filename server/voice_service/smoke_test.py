"""Smoke test da voz clonada: gera uma frase curta e salva em WAV.

Uso: python server/voice_service/smoke_test.py "texto" saida.wav
"""
import sys
import time
from pathlib import Path

import soundfile as sf
import torch

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "server" / "data" / "voice" / "jarvis_ref.wav"

text = sys.argv[1] if len(sys.argv) > 1 else "Sim?"
out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("smoke.wav")

from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # noqa: E402

print("torch", torch.__version__, "cuda", torch.cuda.is_available())
t0 = time.monotonic()
model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
print(f"modelo carregado em {time.monotonic() - t0:.1f}s")

t0 = time.monotonic()
wav = model.generate(text, language_id="pt", audio_prompt_path=str(REF),
                     exaggeration=0.5, cfg_weight=0.5, temperature=0.7)
gen = time.monotonic() - t0
sf.write(str(out), wav.squeeze(0).cpu().numpy(), model.sr)
dur = wav.shape[-1] / model.sr
print(f"OK: {dur:.2f}s de audio em {gen:.1f}s (RTF {gen / dur:.2f}) -> {out}")
