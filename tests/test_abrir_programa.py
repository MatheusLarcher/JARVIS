"""Abrir programa: resolução (unit) e o pedido de verdade pela voz (e2e).

  1) Unit: `resolver()`/`abrir()` contra apps reais desta máquina — sem
     servidor, sem LLM. Cobre: embutido, alias, atalho por aproximação,
     fallback pra app só-da-Store (sem .lnk) e o caso de não achar nada.
  2) E2E: fala de verdade "Jarvis, abre o bloco de notas" pelo WebSocket e
     confere que o Notepad ABRIU DE VERDADE (processo novo), não só que a
     ferramenta foi chamada.

Uso:
  python tests/test_abrir_programa.py            # só o unit
  python tests/test_abrir_programa.py --e2e       # unit + e2e (servidor no ar)
"""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from conexao import ws_url  # noqa: E402
from test_audio_e2e import Session, silence, stream, tts_pcm  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from jarvis.system import apps  # noqa: E402

import websockets  # noqa: E402

URL = ws_url()


def notepad_rodando() -> bool:
    r = subprocess.run(["tasklist", "/fi", "imagename eq notepad.exe"],
                       capture_output=True, text=True)
    return "notepad.exe" in r.stdout.lower()


async def unit() -> bool:
    print("== resolução (sem servidor) ==")
    falhas = []

    def confere(nome, ok_esperado):
        pass

    casos = [
        ("bloco de notas", True),   # embutido
        ("calculadora", True),      # embutido (calc.exe, shim ainda funciona)
        ("navegador", True),        # alias -> atalho real
        ("excel", True),            # atalho por aproximação
        ("whatsapp", True),         # fallback: só existe como app da Store
        ("isso nao existe xyz123 nunca", False),
    ]
    for nome, esperado_ok in casos:
        r = await apps.abrir(nome)
        ok = r["ok"] == esperado_ok
        print(f"  {'OK  ' if ok else 'FALHA'} {nome!r:32s} -> {r}")
        if not ok:
            falhas.append(nome)

    if falhas:
        print(f"\nFALHOU em: {', '.join(falhas)}")
        return False
    print("\nOK: resolução bate com o esperado")
    return True


async def e2e() -> bool:
    print("\n== e2e: 'Jarvis, abre o bloco de notas' pela voz ==")
    if notepad_rodando():
        subprocess.run(["taskkill", "/im", "notepad.exe", "/f"], capture_output=True)
        await asyncio.sleep(1)
    if notepad_rodando():
        print("  FALHOU: já tem um Notepad aberto e não consegui fechar pro teste")
        return False

    audio = await tts_pcm("Jarvis, abre o bloco de notas.")
    async with websockets.connect(URL, max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "device_type": "web",
                                  "network": "wifi-home"}))
        s = Session(ws)
        await asyncio.sleep(1.0)
        mark = len(s.events)
        await stream(s.ws, np.concatenate([audio, silence(1.5)]))

        if not await s.wait_for("wake", mark):
            print("  FALHOU: não reconheceu a chamada")
            return False
        # A abertura em si é local e instantânea (EXECUTING chega em ms); não
        # espera o "speak" — a síntese da confirmação pode demorar bem mais
        # (voz clonada) e isso não deve atrasar a checagem do que importa aqui.
        await s.wait_for("state", mark, state="EXECUTING", timeout=30)
        final = s.seen("stt_final", mark)

        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 10:
            if notepad_rodando():
                break
            await asyncio.sleep(0.3)
        aberto = notepad_rodando()

        speak = await s.wait_for("speak", mark, timeout=120)
        s.task.cancel()

    print(f"  transcrição: {final and final['text']!r}")
    print(f"  falou      : {speak and speak['text']!r}")
    print(f"  Notepad abriu de verdade: {aberto}")
    subprocess.run(["taskkill", "/im", "notepad.exe", "/f"], capture_output=True)

    ok = bool(speak) and aberto
    print("  " + ("OK" if ok else "FALHOU"))
    return ok


async def main() -> int:
    ok = await unit()
    if "--e2e" in sys.argv:
        ok = await e2e() and ok
    print("\n=== TUDO OK ===" if ok else "\n=== FALHOU ===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
