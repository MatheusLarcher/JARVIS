"""Prepara o áudio de referência da voz do JARVIS pra clonagem.

Pega o arquivo bruto, converte pra mono 24kHz, detecta os trechos de fala com o
Silero VAD, descarta silêncio/ruído curto e salva o melhor bloco contínuo
(~8-15s) em server/data/voice/jarvis_ref.wav.

Uso: python server/scripts/prepare_voice_ref.py <arquivo_de_origem>
"""
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "server" / "data" / "voice"
SR = 24000
TARGET_MIN_S = 8.0
TARGET_MAX_S = 15.0


def decode(src: Path, sr: int) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(src), "-f", "s16le", "-ac", "1",
         "-ar", str(sr), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16)


def speech_segments(pcm16k: np.ndarray) -> list[tuple[float, float]]:
    import torch
    from silero_vad import get_speech_timestamps, load_silero_vad
    model = load_silero_vad()
    audio = torch.from_numpy(pcm16k.astype(np.float32) / 32768.0)
    ts = get_speech_timestamps(audio, model, sampling_rate=16000,
                               min_speech_duration_ms=250,
                               min_silence_duration_ms=300)
    return [(t["start"] / 16000, t["end"] / 16000) for t in ts]


def main():
    src = Path(sys.argv[1])
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    segs = speech_segments(decode(src, 16000))
    if not segs:
        print("Nenhuma fala detectada."); sys.exit(1)
    print(f"{len(segs)} trechos de fala:")
    for s, e in segs:
        print(f"  {s:6.2f}s → {e:6.2f}s  ({e - s:.2f}s)")

    # junta trechos vizinhos (pausa curta entre frases) e pega o bloco mais longo
    merged = [list(segs[0])]
    for s, e in segs[1:]:
        if s - merged[-1][1] < 1.0:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    merged.sort(key=lambda b: b[1] - b[0], reverse=True)
    start, end = merged[0]
    if end - start > TARGET_MAX_S:
        end = start + TARGET_MAX_S
    dur = end - start
    print(f"\nEscolhido: {start:.2f}s → {end:.2f}s ({dur:.2f}s)")
    if dur < TARGET_MIN_S:
        print(f"AVISO: referência curta ({dur:.1f}s); a clonagem fica melhor com 8s+.")

    out = OUT_DIR / "jarvis_ref.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ss", f"{start:.3f}",
         "-t", f"{dur:.3f}", "-ac", "1", "-ar", str(SR),
         "-af", "highpass=f=70,loudnorm=I=-18:TP=-2:LRA=9", str(out)],
        check=True)
    print(f"Referência salva: {out}")


if __name__ == "__main__":
    main()
