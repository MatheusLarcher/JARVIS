"""Qual tamanho de Whisper dá a melhor qualidade DENTRO do orçamento de tempo.

O large-v3-turbo é inviável nesta GPU (14,7s/frase). Aqui comparamos os que
rodam rápido, todos com o prompt que faz reconhecer "Jarvis", medindo qualidade
no áudio difícil e tempo.

Uso: python tests/bench_whisper_tamanhos.py
"""
import asyncio
import statistics
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from bench_stt import (acertou_nome, carregar, norm, preparar,  # noqa: E402
                       reconheceu_chamada, so_comando, wer)

PROMPT = ("Conversa com o assistente de voz Jarvis. "
          "Exemplos: Jarvis, liga a luz da sala. "
          "Jarvis, desliga a luz do quarto. Jarvis, que horas são?")

CANDIDATOS = [
    ("base", 1), ("small", 1), ("small", 5), ("medium", 1),
    ("distil-large-v3", 1), ("large-v3", 1),
]


async def main():
    from faster_whisper import WhisperModel

    todas = await preparar()
    dificeis = [a for a in todas if a[2] == "dificil"]
    ruidos = [a for a in todas if a[2] == "ruido"]
    print(f"{len(dificeis)} frases difíceis + {len(ruidos)} com ruído\n")
    print(f"{'modelo':18s} {'beam':>4s} {'acorda':>8s} {'erro difícil':>12s} "
          f"{'erro ruído':>11s} {'s/frase':>8s} {'carga':>7s}")

    for tamanho, beam in CANDIDATOS:
        try:
            t0 = time.perf_counter()
            m = WhisperModel(tamanho, device="cuda", compute_type="float16")
            carga = time.perf_counter() - t0
        except Exception as e:
            print(f"{tamanho:18s} {beam:>4d}  indisponível: {type(e).__name__}")
            continue

        def roda(audio):
            segs, _ = m.transcribe(audio, language="pt", beam_size=beam,
                                   vad_filter=False, condition_on_previous_text=False,
                                   initial_prompt=PROMPT)
            return " ".join(s.text for s in segs).strip()

        roda(carregar(dificeis[0][1]))          # aquece

        acorda, erros_d, erros_r, tempos = 0, [], [], []
        for frase, wav, tipo in dificeis + ruidos:
            audio = carregar(wav)
            t0 = time.perf_counter()
            texto = roda(audio)
            tempos.append(time.perf_counter() - t0)
            hyp = " ".join(p for p in norm(texto) if p != "jarvis")
            erro = wer(so_comando(frase), hyp)
            if tipo == "dificil":
                acorda += reconheceu_chamada(texto)
                erros_d.append(erro)
            else:
                erros_r.append(erro)
        print(f"{tamanho:18s} {beam:>4d} {acorda:>4d}/{len(dificeis):<3d} "
              f"{np.mean(erros_d):>12.3f} {np.mean(erros_r):>11.3f} "
              f"{statistics.median(tempos):>8.2f} {carga:>7.1f}", flush=True)
        del m


asyncio.run(main())
