"""Por que a resposta demora 2,5s se ficou um tempo sem perguntar nada?

O modelo continua carregado e keep_alive não resolveu. A suspeita é a GPU
entrando em economia de energia: a primeira inferência depois de um tempo
ocioso paga o "acordar" da placa.

Compara 20s parado x 20s com pinguinhos periódicos.

Uso: python tests/diag_gpu_ociosa.py     (env jarvis)
"""
import asyncio
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.config import config  # noqa: E402

PERGUNTA = "responda em uma frase: o que e o vento"


def clocks() -> str:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=clocks.sm,pstate,utilization.gpu",
         "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()
    return out


async def pergunta(texto=PERGUNTA, tokens=None) -> float:
    from litellm import acompletion

    from jarvis.agents.agent import _extras_llm
    cfg = config.settings["llm"]
    extras = _extras_llm(cfg)
    if tokens:
        extras["max_tokens"] = tokens
    t0 = time.perf_counter()
    r = await acompletion(model=cfg["model"],
                          messages=[{"role": "user", "content": texto}], **extras)
    _ = r.choices[0].message.content
    return time.perf_counter() - t0


async def main():
    await pergunta()          # aquece
    print(f"estado da GPU logo após usar: {clocks()}")

    print("\nA) 20 segundos parado:")
    await asyncio.sleep(20)
    print(f"   GPU antes: {clocks()}")
    print(f"   resposta em {await pergunta():.2f}s")

    print("\nB) 20 segundos com um pinguinho a cada 5s:")
    for _ in range(4):
        await asyncio.sleep(5)
        await pergunta("oi", tokens=1)
    print(f"   GPU antes: {clocks()}")
    print(f"   resposta em {await pergunta():.2f}s")

    print("\nC) confirmando: mais 20s parado")
    await asyncio.sleep(20)
    print(f"   resposta em {await pergunta():.2f}s")


asyncio.run(main())
