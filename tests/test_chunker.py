"""Unit: corte do texto do LLM em pedaços faláveis.

Uso: python tests/test_chunker.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.tts.chunker import Chunker  # noqa: E402


def pedacos(texto_em_partes, **kw):
    ch = Chunker(**kw)
    out = []
    for parte in texto_em_partes:
        out += list(ch.feed(parte))
    out += list(ch.flush())
    return out


def main():
    fails = 0

    def check(nome, cond, extra=""):
        nonlocal fails
        fails += not cond
        print(("OK  " if cond else "FAIL"), nome, extra)

    # o primeiro pedaço tem que sair cedo (3 palavras), pra voz começar rápido
    r = pedacos(["Claro", ", ", "vou ", "ligar ", "a ", "luz ", "da ", "sala ",
                 "agora ", "mesmo ", "para ", "você."])
    check("primeiro pedaço curto", len(r[0].split()) <= 3, f"-> {r[0]!r}")
    check("nada se perde", " ".join(r).split() ==
          "Claro, vou ligar a luz da sala agora mesmo para você.".split(),
          f"-> {r}")

    # pedaços crescem (menos chamadas de TTS depois do começo)
    texto = " ".join(f"palavra{i}" for i in range(60))
    r = pedacos([texto])
    tamanhos = [len(p.split()) for p in r]
    check("pedaços crescem", tamanhos[0] <= 3 and tamanhos[-1] >= tamanhos[0],
          f"-> {tamanhos}")
    check("respeita o máximo", max(tamanhos) <= 14, f"-> {tamanhos}")

    # corta em fim de frase quando dá
    r = pedacos(["Pronto. ", "A luz da sala está acesa agora, senhor."])
    check("corta na pontuação", r[0].endswith("."), f"-> {r[0]!r}")

    # chega em pedacinhos de letra (como vem do LLM em stream)
    frase = "Sim, senhor. Já liguei a luz."
    r = pedacos(list(frase))
    check("funciona letra a letra", " ".join(r).split() == frase.split(), f"-> {r}")

    # texto curto: sai inteiro no flush
    r = pedacos(["Pronto."])
    check("texto curto sai inteiro", r == ["Pronto."], f"-> {r}")

    print("\n" + ("TODOS OS TESTES PASSARAM" if fails == 0 else f"{fails} FALHAS"))
    sys.exit(1 if fails else 0)


main()
