"""Unit: a resposta falada é cortada na primeira frase.

Roda sem GPU e sem servidor.
Uso: python tests/test_corte_resposta.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.agents.agent import _CortaResposta  # noqa: E402


def passa(partes, **kw) -> str:
    c = _CortaResposta(**kw)
    return "".join(c.feed(p) for p in partes)


def main():
    fails = 0

    def check(nome, obtido, esperado):
        nonlocal fails
        ok = obtido == esperado
        fails += not ok
        print(("OK  " if ok else "FAIL"), nome, f"-> {obtido!r}")

    check("frase única passa inteira",
          passa(["Canberra é a capital da Austrália."]),
          "Canberra é a capital da Austrália.")

    check("corta na primeira frase",
          passa(["Canberra é a capital. Fica no sudeste do país e tem 400 mil habitantes."]),
          "Canberra é a capital.")

    # é assim que o texto chega do modelo: token a token
    check("corta mesmo chegando picado",
          passa(["Can", "berra ", "é a ", "capital", ". ", "Além disso", " fica no sul."]),
          "Canberra é a capital.")

    check("estourou o tamanho, fecha a frase",
          passa(["uma resposta muito longa que continua sem nunca colocar ponto "
                 "final em lugar nenhum e segue falando"], max_palavras=8),
          "uma resposta muito longa que continua sem nunca."),

    check("não engasga com texto vazio", passa([""]), "")

    c = _CortaResposta()
    c.feed("Pronto.")
    check("marca que terminou", c.encerrado, True)

    print("\n" + ("TODOS OS TESTES PASSARAM" if fails == 0 else f"{fails} FALHAS"))
    sys.exit(1 if fails else 0)


main()
