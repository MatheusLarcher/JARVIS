"""Unit: reconhecimento de "jarvis" na transcrição + separação do comando.

Uso: python tests/test_wakeword.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.audio.wakeword import matcher  # noqa: E402

CASES = [
    # (transcrição do STT, chamou?, comando esperado)
    ("Jarvis", True, ""),
    ("Jarvis.", True, ""),
    ("Jarvis, liga a luz da sala", True, "liga a luz da sala"),
    ("jarvis liga a luz", True, "liga a luz"),
    ("Liga a luz da sala, Jarvis", True, "liga a luz da sala"),
    ("Hey Jarvis, que horas são?", True, "que horas sao"),
    ("Ei Jarvis, apaga a luz", True, "apaga a luz"),
    # variações que o STT costuma escrever
    ("Jarves, liga a luz", True, "liga a luz"),
    ("Jarvez", True, ""),
    ("Javis, desliga a luz", True, "desliga a luz"),
    ("Jarvis liga a luz da sala por favor", True, "liga a luz da sala por favor"),
    # capturados no microfone real (o STT parte ou troca letras do nome)
    ("Já fiz libe a luz da sala.", True, "libe a luz da sala"),
    ("Jar vis, liga a luz", True, "liga a luz"),
    ("Jarbis, que horas são", True, "que horas sao"),

    # não deve disparar
    ("liga a luz da sala", False, ""),
    ("hoje o dia foi bom", False, ""),
    ("já vi esse filme", False, ""),
    ("vamos jantar", False, ""),
    ("já era tarde", False, ""),
    ("o carro é novo", False, ""),
    ("", False, ""),
]


def main():
    fails = 0
    for text, want_hit, want_cmd in CASES:
        hit, cmd = matcher.match(text)
        ok = (hit == want_hit) and (not want_hit or cmd == want_cmd)
        fails += not ok
        print(("OK  " if ok else "FAIL"), f"{text!r} -> hit={hit} cmd={cmd!r}")
    print("\n" + ("TODOS OS TESTES PASSARAM" if fails == 0 else f"{fails} FALHAS"))
    sys.exit(1 if fails else 0)


main()
