"""Por que o initial_prompt deixa o Whisper 10x mais lento — e dá pra evitar?

O prompt é o que faz o modelo reconhecer "Jarvis" em áudio ruim, mas no
large-v3-turbo ele custou ~3s por frase. Aqui testamos tamanhos de prompt e
alternativas, medindo qualidade E tempo no áudio difícil.

Uso: python tests/bench_whisper_prompt.py
"""
import asyncio
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from bench_stt import (FRASES, acertou_nome, carregar, norm,  # noqa: E402
                       preparar, reconheceu_chamada, so_comando, wer)

VARIACOES = {
    "sem nada": dict(),
    "prompt 1 palavra": dict(initial_prompt="Jarvis."),
    "prompt curto": dict(initial_prompt="Falando com o Jarvis."),
    "prompt medio": dict(initial_prompt="Conversa com o assistente de voz Jarvis. "
                                        "Jarvis, liga a luz da sala."),
    "prompt longo": dict(initial_prompt="Conversa com o assistente de voz Jarvis. "
                                        "Exemplos: Jarvis, liga a luz da sala. "
                                        "Jarvis, desliga a luz do quarto. "
                                        "Jarvis, que horas são? Jarvis, abre o navegador."),
    "hotword so nome": dict(hotwords="Jarvis"),
    "hotwords casa": dict(hotwords="Jarvis sala quarto escritorio luz"),
}


async def main():
    from faster_whisper import WhisperModel

    amostras = [a for a in await preparar() if a[2] == "dificil"]
    print(f"{len(amostras)} amostras difíceis (microfone longe + ruído)\n")

    modelo = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")

    print(f"{'variação':20s} {'acorda':>8s} {'nome ok':>8s} {'erro cmd':>9s} {'s/frase':>8s}")
    for nome, extra in VARIACOES.items():
        acorda = nome_ok = 0
        erros, tempos = [], []
        for frase, wav, _ in amostras:
            audio = carregar(wav)
            t0 = time.monotonic()
            segs, _info = modelo.transcribe(
                audio, language="pt", beam_size=1, vad_filter=False,
                condition_on_previous_text=False, **extra)
            texto = " ".join(s.text for s in segs).strip()
            tempos.append(time.monotonic() - t0)
            acorda += reconheceu_chamada(texto)
            nome_ok += acertou_nome(texto)
            hyp = " ".join(p for p in norm(texto) if p != "jarvis")
            erros.append(wer(so_comando(frase), hyp))
        print(f"{nome:20s} {acorda:>4d}/{len(amostras):<3d} {nome_ok:>4d}/{len(amostras):<3d} "
              f"{np.mean(erros):>9.3f} {np.mean(tempos):>8.2f}")


asyncio.run(main())
