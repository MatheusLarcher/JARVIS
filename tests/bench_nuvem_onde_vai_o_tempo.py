"""Onde vai o tempo da resposta da nuvem: pensando ou no caminho até o modelo?

Mede tudo INTERCALADO, no mesmo instante, porque a API oscila muito (medir A e
depois B faz a oscilação virar "diferença" — foi exatamente o que me enganou na
primeira medição, que sugeriu um ganho 3x maior do que o real).

Responde três coisas:
  0. o `reasoning_effort` está mesmo sendo repassado pelo ADK?
  1. low vs high pelo agente -> quanto o "pensar" custa
  2. crua vs pelo agente     -> quanto custa o ADK + o prompt do JARVIS

Uso: python tests/bench_nuvem_onde_vai_o_tempo.py
"""
import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.agents import agent as adk_agent  # noqa: E402
from jarvis.agents import especialistas  # noqa: E402
from jarvis.config import config  # noqa: E402
from jarvis.context.engine import context_engine  # noqa: E402
from jarvis.memory.db import store  # noqa: E402

PERGUNTAS = [
    "energia solar ou eolica compensa mais numa casa",
    "vale a pena trocar de carro com 100 mil km",
    "qual a melhor hora do dia pra correr",
]
RODADAS = 3
SISTEMA = ("Você é o JARVIS. Responda em português do Brasil, em UMA frase "
           "curta, sem markdown — sua resposta é falada em voz alta.")


def usa(valor):
    if valor is None:
        config.settings["nuvem"].pop("reasoning_effort", None)
    else:
        config.settings["nuvem"]["reasoning_effort"] = valor
    especialistas._construidos.clear()


async def via_agente(ctx, pergunta):
    t0 = time.perf_counter()
    async for _ in adk_agent.ask_stream(pergunta, ctx, "avancado"):
        return time.perf_counter() - t0
    return None


async def via_crua(pergunta, esforco):
    from litellm import acompletion
    modelo, extras = especialistas.nuvem_disponivel()
    extras = dict(extras)
    if esforco:
        extras["reasoning_effort"] = esforco
    else:
        extras.pop("reasoning_effort", None)
    t0 = time.perf_counter()
    r = await acompletion(model=modelo,
                          messages=[{"role": "system", "content": SISTEMA},
                                    {"role": "user", "content": pergunta}],
                          stream=True, **extras)
    async for pedaco in r:
        if pedaco.choices[0].delta.content or "":
            return time.perf_counter() - t0
    return None


async def main():
    await store.open()
    ctx = context_engine.register("web-dev", {"device_type": "web"})
    original = config.settings["nuvem"].get("reasoning_effort")

    # 0) prova que o parâmetro chega no modelo: com um valor inválido a chamada
    #    tem que morrer (se fosse ignorado, responderia normal)
    usa("nivel_que_nao_existe")
    respondeu = False
    async for _ in adk_agent.ask_stream(PERGUNTAS[0], ctx, "avancado"):
        respondeu = True
        break
    print("0) o reasoning_effort é repassado pelo ADK? "
          + ("SIM (valor inválido derrubou a chamada)" if not respondeu
             else "NÃO — está sendo IGNORADO!"))

    usa("low")
    await via_agente(ctx, "oi")        # aquece

    medidas = {"agente low": [], "agente high": [],
               "crua low": [], "crua high": []}
    for r in range(RODADAS):
        for pergunta in PERGUNTAS:
            for esforco in ("low", "high"):
                usa(esforco)
                t = await via_agente(ctx, pergunta)
                if t:
                    medidas[f"agente {esforco}"].append(t)
                t = await via_crua(pergunta, esforco)
                if t:
                    medidas[f"crua {esforco}"].append(t)
        print(f"   rodada {r + 1} ok")

    print("\ntempo até a 1a palavra (mediana de "
          f"{RODADAS * len(PERGUNTAS)} medições cada):\n")
    for rotulo, v in medidas.items():
        if v:
            print(f"   {rotulo:12s} {statistics.median(v):5.2f}s   "
                  f"(melhor {min(v):.2f}s, pior {max(v):.2f}s)")

    def med(k):
        return statistics.median(medidas[k]) if medidas[k] else 0

    print(f"\n   pensar high em vez de low custa: {med('crua high') - med('crua low'):+.2f}s "
          f"(crua) / {med('agente high') - med('agente low'):+.2f}s (agente)")
    print(f"   o caminho do agente (ADK + prompt) custa: "
          f"{med('agente low') - med('crua low'):+.2f}s")

    usa(original)
    await store.close()
    return 0


sys.exit(asyncio.run(main()))
