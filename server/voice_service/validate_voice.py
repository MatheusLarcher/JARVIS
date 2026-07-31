"""Valida a voz clonada de forma objetiva.

Usa o VoiceEncoder TREINADO que vem dentro do modelo Chatterbox (instanciar
VoiceEncoder() direto dá pesos aleatórios e similaridade falsa de 1.000).
Compara o embedding de locutor entre a referência, a voz clonada e a voz antiga.

Uso: python server/voice_service/validate_voice.py <gerado.wav> [baseline.mp3 ...]
"""
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "server" / "data" / "voice" / "jarvis_ref.wav"


def load16k(path: Path) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1",
         "-ar", "16000", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def main():
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
    enc = model.ve   # encoder com pesos treinados

    def emb(p: Path):
        return np.array(enc.embeds_from_wavs([load16k(p)], sample_rate=16000)[0])

    ref = emb(REF)

    def cos(a, b):
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    print(f"\n{'arquivo':40s} similaridade com a referência")
    for arg in sys.argv[1:]:
        p = Path(arg)
        print(f"{p.name:40s} {cos(ref, emb(p)):.3f}")


if __name__ == "__main__":
    main()
