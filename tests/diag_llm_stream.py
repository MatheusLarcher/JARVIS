"""Mostra exatamente como o texto do LLM chega (deltas ou acumulado) e o tempo
de cada trecho. Serve pra ajustar o corte em pedaços faláveis.

Uso: python tests/diag_llm_stream.py ["pergunta"]
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.agents import agent  # noqa: E402
from jarvis.context.engine import context_engine  # noqa: E402
from jarvis.memory.db import store  # noqa: E402

PERGUNTA = sys.argv[1] if len(sys.argv) > 1 else \
    "me explica em duas frases o que e um buraco negro"


async def main():
    await store.open()
    ctx = context_engine.register("pc-matheus", {"device_type": "pc"})

    # duas rodadas: a 1ª paga a construção do agente, a 2ª mostra o custo real
    for rodada in (1, 2):
        t0 = time.perf_counter()
        n, primeiro, acumulado = 0, None, ""
        async for novo in agent.ask_stream(PERGUNTA, ctx):
            n += 1
            if primeiro is None:
                primeiro = time.perf_counter() - t0
            acumulado += novo
            if rodada == 1 and n <= 3:
                print(f"  [{time.perf_counter() - t0:5.2f}s] {novo!r}")
        print(f"rodada {rodada}: 1ª palavra em {primeiro:.2f}s | "
              f"tudo em {time.perf_counter() - t0:.1f}s ({n} trechos)")
    print(f"\núltima resposta: {acumulado[:120]!r}")
    await store.close()


asyncio.run(main())
