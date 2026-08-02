"""O agente da nuvem (GPT-5.6 Luna) responde de verdade?

O roteador é um modelo pequeno e escolhe diferente a cada vez, então esperar
que ele mande pro "avancado" pra testar a nuvem é frágil. Aqui a gente força
cada agente e confere que todos respondem.

Precisa da chave da OpenAI no config/.env e do Ollama no ar.
Uso: python tests/test_agente_nuvem.py
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.agents import agent as adk_agent  # noqa: E402
from jarvis.agents.especialistas import _modelo_do_agente  # noqa: E402
from jarvis.agents.roteador import agentes_disponiveis  # noqa: E402
from jarvis.context.engine import context_engine  # noqa: E402
from jarvis.memory.db import store  # noqa: E402

PERGUNTA = {
    "casa": "que dispositivos você controla aqui",
    "sistema": "você consegue abrir programas no computador",
    "conversa": "em que ano o Brasil foi descoberto",
    "avancado": "energia solar ou eólica compensa mais numa casa, e por quê",
}


async def main():
    # o prompt do agente busca o histórico curto no SQLite
    await store.open()
    ctx = context_engine.register("web-dev", {"device_type": "web"})
    fails = 0
    for a in agentes_disponiveis():
        nome = a["nome"]
        modelo, _ = _modelo_do_agente(nome)
        onde = "NUVEM" if a.get("requer_nuvem") else "local"
        print(f"\n== {nome} ({onde}: {modelo}) ==")
        print(f"   pergunta: {PERGUNTA[nome]!r}")
        t0 = time.perf_counter()
        try:
            resposta = await adk_agent.ask(PERGUNTA[nome], ctx, agente=nome)
        except Exception as e:
            resposta, erro = None, e
            print(f"   ERRO: {type(e).__name__}: {e}")
        dt = time.perf_counter() - t0
        ok = bool(resposta and resposta.strip())
        fails += not ok
        print(f"   {dt:5.2f}s  {'OK  ' if ok else 'FALHOU'} {(resposta or '')[:110]!r}")

    await store.close()
    print("\n" + ("TODOS OS AGENTES RESPONDERAM" if fails == 0
                  else f"{fails} AGENTE(S) MUDO(S)"))
    sys.exit(1 if fails else 0)


asyncio.run(main())
