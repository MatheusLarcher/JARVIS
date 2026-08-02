"""O Ollama está descarregando o modelo entre as perguntas?

Se estiver, cada pergunta paga o recarregamento (~2s num modelo de 1 GB).
Compara chamadas seguidas, com pausa e com keep_alive.

Uso: python tests/diag_ollama_keepalive.py     (env jarvis)
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.config import config  # noqa: E402

PERGUNTA = "responda em uma frase: o que e o sol"


async def uma(extra: dict) -> float:
    from litellm import acompletion

    from jarvis.agents.agent import _extras_llm
    cfg = config.settings["llm"]
    t0 = time.perf_counter()
    r = await acompletion(model=cfg["model"],
                          messages=[{"role": "user", "content": PERGUNTA}],
                          **{**_extras_llm(cfg), **extra})
    _ = r.choices[0].message.content
    return time.perf_counter() - t0


async def carregado() -> str:
    import httpx
    async with httpx.AsyncClient() as c:
        r = await c.get("http://127.0.0.1:11434/api/ps")
    modelos = r.json().get("models", [])
    return ", ".join(f"{m['name']} (até {m.get('expires_at', '?')[:19]})"
                     for m in modelos) or "nenhum"


async def main():
    print(f"modelo carregado agora: {await carregado()}\n")

    print("A) três perguntas seguidas, sem pausa:")
    for i in range(3):
        print(f"   {i + 1}ª: {await uma({}):.2f}s")

    print("\nB) com 20s de pausa entre elas (simula uso real):")
    for i in range(2):
        await asyncio.sleep(20)
        print(f"   depois da pausa: {await uma({}):.2f}s "
              f"| carregado: {await carregado()}")

    print("\nC) mesma coisa, mas pedindo pro Ollama manter o modelo na memória:")
    for i in range(2):
        await asyncio.sleep(20)
        print(f"   depois da pausa: {await uma({'keep_alive': '30m'}):.2f}s")


asyncio.run(main())
