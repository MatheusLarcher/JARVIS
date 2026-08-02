"""Unit: a decisão do roteador nunca trava o JARVIS.

Modelo pequeno responde fora do formato o tempo todo — o que importa é que
sempre saia uma decisão utilizável.

Roda sem GPU e sem servidor.
Uso: python tests/test_roteador.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.agents.roteador import agentes_disponiveis, interpretar  # noqa: E402

AGENTES = agentes_disponiveis()
NOMES = [a["nome"] for a in AGENTES]

CASOS = [
    # (o que o modelo cuspiu, agente esperado, tem resposta direta?)
    ("AGENTE: casa", "casa", False),
    ("agente: conversa", "conversa", False),
    ("AGENTE:sistema", "sistema", False),
    ("  AGENTE: casa  ", "casa", False),
    ("RESPOSTA: São nove horas.", None, True),
    ('RESPOSTA: "Só um momento, senhor."', None, True),
    # nome inválido mas parecido → aproveita
    ("AGENTE: casas", "casa", False),
    ("AGENTE: convers", "conversa", False),
    # fora do formato, mas cita um agente
    ("Acho que isso é da casa mesmo.", "casa", False),
    # lixo completo → cai no padrão, sem travar
    ("sei lá", None, False),
    ("", None, False),
]


def main():
    print(f"agentes configurados: {NOMES}\n")
    fails = 0
    for texto, esperado, tem_resposta in CASOS:
        d = interpretar(texto, AGENTES)
        ok = True
        if tem_resposta:
            ok = bool(d.resposta) and d.agente is None
        elif esperado is not None:
            ok = d.agente == esperado
        else:
            # sem esperado: só não pode inventar agente que não existe
            ok = d.agente is None or d.agente in NOMES
        fails += not ok
        print(("OK  " if ok else "FAIL"),
              f"{texto[:38]!r:42s} -> agente={d.agente!r} "
              f"resposta={(d.resposta or '')[:24]!r} ({d.confianca})")

    # nunca pode devolver um agente inexistente
    inventados = [interpretar(t, AGENTES).agente for t, _, _ in CASOS]
    if any(a is not None and a not in NOMES for a in inventados):
        print("FALHA: inventou agente fora da lista")
        fails += 1

    print("\n" + ("TODOS OS TESTES PASSARAM" if fails == 0 else f"{fails} FALHAS"))
    sys.exit(1 if fails else 0)


main()
