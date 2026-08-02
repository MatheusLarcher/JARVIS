"""A primeira pergunta pra nuvem é mais lenta que as seguintes?

O aquecimento do start monta os agentes e acorda o modelo LOCAL, mas nunca
encosta no provedor externo — então a primeira pergunta difícil do dia pagaria
a conexão (DNS + TLS + cliente do litellm) na frente do usuário.

Mede a mesma pergunta 3 vezes seguidas, num processo novo (= servidor recém
reiniciado). Se a 1a for muito pior, o aquecimento precisa incluir a nuvem.

Uso: python tests/bench_nuvem_primeira_chamada.py [--aquecendo]
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.agents import agent as adk_agent  # noqa: E402
from jarvis.context.engine import context_engine  # noqa: E402
from jarvis.memory.db import store  # noqa: E402

PERGUNTA = "energia solar ou eolica compensa mais numa casa"


async def primeira_palavra(ctx):
    t0 = time.perf_counter()
    async for _ in adk_agent.ask_stream(PERGUNTA, ctx, "avancado"):
        return time.perf_counter() - t0
    return None


async def main():
    aquecendo = "--aquecendo" in sys.argv
    await store.open()
    ctx = context_engine.register("web-dev", {"device_type": "web"})

    if aquecendo:
        t0 = time.perf_counter()
        await adk_agent.aquecer()
        print(f"aquecimento do start: {time.perf_counter() - t0:.2f}s\n")
    else:
        print("SEM aquecer a nuvem (como estava antes)\n")

    tempos = []
    for i in range(3):
        t = await primeira_palavra(ctx)
        tempos.append(t)
        print(f"   pergunta {i + 1}: 1a palavra em {t:5.2f}s")

    if tempos[0] and tempos[1]:
        print(f"\n   a 1a custou {tempos[0] - min(tempos[1:]):+.2f}s a mais "
              "que as seguintes")
    await store.close()
    return 0


sys.exit(asyncio.run(main()))
