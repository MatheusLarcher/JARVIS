"""Quanto custa e quanto acerta a decisão — na ordem que roda de verdade.

  1. Intent Router local (regex): custo zero. Se acertar aqui, o LLM nem entra.
  2. Roteador (modelo pequeno): escolhe o agente. O tempo dele SOMA na latência.

Por isso o teste mede as DUAS camadas: adiantaria pouco um roteador rápido se
o que é frequente não fosse resolvido antes dele.

Precisa do Ollama no ar (o servidor do JARVIS não precisa estar rodando).
Uso: python tests/bench_roteador.py
"""
import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.agents.roteador import agentes_disponiveis, decidir  # noqa: E402
from jarvis.intents.router import intent_router  # noqa: E402

# (frase, destinos aceitáveis) — "local" = resolvido sem LLM;
# None = o roteador respondeu direto
CASOS = [
    ("liga a luz da sala", {"local", "casa"}),
    ("desliga a luz do quarto", {"local", "casa"}),
    ("que temperatura está aqui", {"local", "casa"}),
    ("que horas são", {"local"}),
    ("bom dia", {"local"}),
    ("obrigado", {"local"}),
    ("abre o navegador", {"sistema"}),
    ("aumenta o volume", {"sistema"}),
    ("como você está", {"sistema", "conversa", None}),
    ("quem foi santos dumont", {"conversa"}),
    ("me conta uma curiosidade", {"conversa"}),
    ("põe um alarme pras sete da manhã", {"sistema", "casa"}),
    ("compara duas opções e me diz qual é melhor", {"avancado", "conversa"}),
    ("planeja meu dia de amanhã", {"avancado", "conversa"}),
]


async def main():
    print(f"agentes: {[a['nome'] for a in agentes_disponiveis()]}\n")
    print("aquecendo...")
    await decidir("teste")

    tempos, acertos, linhas = [], 0, []
    for frase, aceitas in CASOS:
        t0 = time.perf_counter()
        m = intent_router.match(frase)
        if m:
            dt, escolha, resposta, conf = time.perf_counter() - t0, "local", None, m.intent_id
        else:
            d, _ = await decidir(frase)
            dt = time.perf_counter() - t0
            escolha = None if d.resposta else d.agente
            resposta, conf = d.resposta, d.confianca
            tempos.append(dt)
        ok = escolha in aceitas
        acertos += ok
        linhas.append((ok, frase, escolha, resposta, dt, conf))

    for ok, frase, escolha, resposta, dt, conf in linhas:
        alvo = (f"resposta direta: {resposta[:34]!r}" if resposta
                else ("LOCAL, sem LLM" if escolha == "local" else f"-> {escolha}"))
        print(f"{'OK  ' if ok else 'ERRO'} {dt*1000:6.0f}ms  {frase[:42]:44s} "
              f"{alvo} ({conf})")

    locais = sum(1 for l in linhas if l[2] == "local")
    print(f"\nacerto de destino: {acertos}/{len(CASOS)}")
    print(f"resolvidos sem LLM (0ms): {locais}/{len(CASOS)}")
    if tempos:
        print(f"custo do roteador quando entra: media {statistics.mean(tempos):.2f}s | "
              f"mediana {statistics.median(tempos):.2f}s | "
              f"pior {max(tempos):.2f}s | melhor {min(tempos):.2f}s")


asyncio.run(main())
