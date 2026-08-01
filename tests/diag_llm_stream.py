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
    t0 = time.perf_counter()
    n = 0
    acumulado = ""
    async for novo in agent.ask_stream(PERGUNTA, ctx):
        n += 1
        t = time.perf_counter() - t0
        acumulado += novo
        marca = ""
        if novo.startswith(" "):
            marca += " [começa com espaço]"
        if novo.endswith(" "):
            marca += " [termina com espaço]"
        print(f"[{t:5.2f}s] #{n:3d} {novo!r}{marca}")
    print(f"\ntotal: {n} trechos em {time.perf_counter() - t0:.1f}s")
    print(f"texto: {acumulado!r}")
    await store.close()


asyncio.run(main())
