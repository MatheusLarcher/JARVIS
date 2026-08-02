"""Mede com precisão o custo do initial_prompt no Whisper.

Diferente dos outros: carrega UM modelo por vez, faz aquecimento (a primeira
chamada sempre mente) e repete cada medição, reportando a mediana.

Uso: python tests/bench_whisper_latencia.py
"""
import asyncio
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from bench_stt import carregar, preparar  # noqa: E402

REPETICOES = 3
PROMPT_CURTO = "Jarvis."
PROMPT_LONGO = ("Conversa com o assistente de voz Jarvis. "
                "Exemplos: Jarvis, liga a luz da sala. "
                "Jarvis, desliga a luz do quarto. Jarvis, que horas são?")


def mede(modelo, audios, **extra) -> float:
    """Mediana do tempo por frase, já descontando o aquecimento."""
    list(modelo.transcribe(audios[0], language="pt", beam_size=1,
                           vad_filter=False, condition_on_previous_text=False,
                           **extra)[0])                      # aquece
    tempos = []
    for _ in range(REPETICOES):
        for audio in audios:
            t0 = time.perf_counter()
            list(modelo.transcribe(audio, language="pt", beam_size=1,
                                   vad_filter=False,
                                   condition_on_previous_text=False, **extra)[0])
            tempos.append(time.perf_counter() - t0)
    return statistics.median(tempos)


async def main():
    from faster_whisper import WhisperModel

    amostras = [a for a in await preparar() if a[2] == "dificil"][:4]
    audios = [carregar(w) for _, w, _ in amostras]
    dur = sum(len(a) for a in audios) / 16000 / len(audios)
    print(f"{len(audios)} frases de ~{dur:.1f}s, {REPETICOES}x cada, GPU livre\n")

    for tamanho in ("large-v3-turbo", "small", "base"):
        try:
            t0 = time.perf_counter()
            m = WhisperModel(tamanho, device="cuda", compute_type="float16")
            carga = time.perf_counter() - t0
        except Exception as e:
            print(f"{tamanho}: indisponível ({type(e).__name__})")
            continue
        sem = mede(m, audios)
        curto = mede(m, audios, initial_prompt=PROMPT_CURTO)
        longo = mede(m, audios, initial_prompt=PROMPT_LONGO)
        hot = mede(m, audios, hotwords="Jarvis sala quarto escritorio luz")
        print(f"{tamanho:16s} carga {carga:4.1f}s | sem prompt {sem:5.2f}s | "
              f"prompt curto {curto:5.2f}s | prompt longo {longo:5.2f}s | "
              f"hotwords {hot:5.2f}s")
        del m


asyncio.run(main())
