"""Unit: o Whisper devolvendo o próprio prompt não pode virar pedido.

Em silêncio, o modelo repete o initial_prompt ("Falando com o Jarvis.") — e
como tem "Jarvis" dentro, isso passava pelo wake word e chegou a acionar um
agente de verdade (visto no E2E de 02/08/2026).

Roda sem GPU e sem servidor.
Uso: python tests/test_eco_prompt.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.stt.whisper import WhisperStt  # noqa: E402

# (texto que o Whisper devolveu, é eco?)
CASOS = [
    ("Falando com o Jarvis.", True),
    ("falando com o jarvis", True),
    ("Falando com o Jarvis. Falando com o Jarvis.", True),
    ("falando com falando com o jarvis f", True),
    ("  Falando com o Jarvis  ", True),
    ("", False),
    # pedidos de verdade não podem ser descartados
    ("Jarvis, liga a luz da sala", False),
    ("liga a luz da sala", False),
    ("jarvis", False),
    ("Falando com o Jarvis sobre energia solar", False),
    ("bom dia", False),
    ("quem foi santos dumont", False),
]


def main():
    stt = WhisperStt.__new__(WhisperStt)   # sem carregar modelo: só a lógica
    stt.contexto = "Falando com o Jarvis."
    from jarvis.stt.whisper import _palavras
    stt._palavras_prompt = set(_palavras(stt.contexto))

    fails = 0
    for texto, esperado in CASOS:
        got = stt._eco(texto)
        ok = got == esperado
        fails += not ok
        print(("OK  " if ok else "FAIL"),
              f"{texto[:44]!r:48s} eco={got} (esperado {esperado})")

    print("\n" + ("TODOS OS TESTES PASSARAM" if fails == 0 else f"{fails} FALHAS"))
    sys.exit(1 if fails else 0)


main()
