"""O Whisper grande está mesmo usando a GPU?

O large-v3-turbo levou 8s por frase e o small 0,14s — diferença grande demais.
Aqui comparamos device/compute_type e olhamos a VRAM ocupada: se o modelo não
sobe pra GPU, o tempo na "cuda" fica igual ao da CPU.

Uso: python tests/diag_whisper_gpu.py
"""
import asyncio
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from bench_stt import carregar, preparar  # noqa: E402


def vram_mb() -> int:
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                          "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout.strip()
    return int(out.splitlines()[0])


def mede(m, audios) -> float:
    list(m.transcribe(audios[0], language="pt", beam_size=1, vad_filter=False)[0])
    tempos = []
    for audio in audios:
        t0 = time.perf_counter()
        list(m.transcribe(audio, language="pt", beam_size=1, vad_filter=False)[0])
        tempos.append(time.perf_counter() - t0)
    return statistics.median(tempos)


async def main():
    from faster_whisper import WhisperModel

    amostras = [a for a in await preparar() if a[2] == "dificil"][:3]
    audios = [carregar(w) for _, w, _ in amostras]
    print(f"{len(audios)} frases de ~{len(audios[0]) / 16000:.1f}s\n")
    print(f"{'modelo':16s} {'device':6s} {'compute':14s} {'VRAM+':>7s} {'s/frase':>8s}")

    combos = [
        ("large-v3-turbo", "cuda", "float16"),
        ("large-v3-turbo", "cuda", "int8_float16"),
        ("large-v3-turbo", "cuda", "int8"),
        ("large-v3-turbo", "cpu", "int8"),
        ("small", "cuda", "float16"),
        ("small", "cpu", "int8"),
    ]
    for tamanho, device, compute in combos:
        antes = vram_mb()
        try:
            m = WhisperModel(tamanho, device=device, compute_type=compute)
        except Exception as e:
            print(f"{tamanho:16s} {device:6s} {compute:14s}  falhou: "
                  f"{type(e).__name__}: {str(e)[:60]}")
            continue
        # a VRAM só sobe de verdade depois da primeira transcrição
        list(m.transcribe(audios[0], language="pt", beam_size=1, vad_filter=False)[0])
        usou = vram_mb() - antes
        t = mede(m, audios)
        print(f"{tamanho:16s} {device:6s} {compute:14s} {usou:>6d}M {t:>8.2f}")
        del m


asyncio.run(main())
