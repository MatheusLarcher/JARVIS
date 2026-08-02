"""Unit: o raciocínio do modelo (<think>...</think>) não pode virar fala.

Roda sem GPU e sem servidor.
Uso: python tests/test_filtro_pensamento.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.agents.agent import _FiltroPensamento  # noqa: E402


def passa(partes) -> str:
    f = _FiltroPensamento()
    return "".join(f.feed(p) for p in partes)


def main():
    fails = 0

    def check(nome, obtido, esperado):
        nonlocal fails
        ok = obtido == esperado
        fails += not ok
        print(("OK  " if ok else "FAIL"), nome, f"-> {obtido!r}")

    check("texto normal passa inteiro",
          passa(["Santos Dumont ", "foi um inventor."]),
          "Santos Dumont foi um inventor.")

    check("bloco de raciocínio some",
          passa(["<think>vou pensar aqui</think>", "A resposta é 42."]),
          "A resposta é 42.")

    check("raciocínio no meio some",
          passa(["Olá. <think>hmm</think> Tudo bem?"]),
          "Olá.  Tudo bem?")

    # o texto chega em pedaços: a tag pode vir partida no meio
    check("tag partida entre pedaços",
          passa(["Oi. <thi", "nk>segredo</thi", "nk> Fim."]),
          "Oi.  Fim.")

    check("raciocínio ainda aberto não vaza",
          passa(["<think>ainda pensando..."]),
          "")

    check("letra a letra",
          passa(list("Certo.<think>x</think>Pronto.")),
          "Certo.Pronto.")

    print("\n" + ("TODOS OS TESTES PASSARAM" if fails == 0 else f"{fails} FALHAS"))
    sys.exit(1 if fails else 0)


main()
