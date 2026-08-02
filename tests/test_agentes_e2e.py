"""E2E dos agentes: fala de verdade pelo WebSocket e confere onde cada pedido
foi parar — e se o registro guardou o áudio e a decisão.

Cenários (cada um exercita um caminho diferente da decisão):
  1) "Jarvis, liga a luz da sala"  -> intent local, sem LLM
  2) "Jarvis, bom dia"             -> saudação pronta, sem LLM
  3) "Jarvis, quem foi Santos Dumont" -> roteador -> agente de conversa

Depois: confere na base se cada interação virou registro com WAV no disco.

Uso: python tests/test_agentes_e2e.py     (servidor no ar na 8040)
"""
import asyncio
import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_audio_e2e import Session, silence, stream, tts_pcm  # noqa: E402

import websockets  # noqa: E402

URL = "ws://127.0.0.1:8040/ws/web-dev?token=tk_web_3Za5Xb7Vc9Td1Rf4Pg6Nh8Lj2"
DATA = Path(__file__).resolve().parents[1] / "server" / "data"
DB = DATA / "jarvis.db"

CENARIOS = [
    ("Jarvis, liga a luz da sala.", "intent local (sem LLM)"),
    ("Jarvis, bom dia.", "saudação pronta (sem LLM)"),
    ("Jarvis, quem foi Santos Dumont?", "roteador → agente local"),
    ("Jarvis, compare energia solar com energia eólica e diga qual compensa mais.",
     "roteador → agente avançado (nuvem)"),
]


def registros_recentes(desde: float) -> list[dict]:
    if not DB.exists():
        return []
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        cur = con.execute(
            "SELECT ts, transcricao, audio_path, agente, rota_json, resposta "
            "FROM registros WHERE ts > ? ORDER BY id", (desde,))
        cols = ["ts", "transcricao", "audio_path", "agente", "rota", "resposta"]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()


async def roda(s: Session, frase: str, esperado: str) -> bool:
    print(f"\n== {frase!r}  ({esperado}) ==")
    audio = await tts_pcm(frase)
    mark = len(s.events)
    t0 = time.perf_counter()
    await stream(s.ws, np.concatenate([audio, silence(1.5)]))

    if not await s.wait_for("wake", mark):
        print("   FALHOU: não reconheceu a chamada")
        return False
    speak = await s.wait_for("speak", mark, timeout=60)
    # resposta longa demora: a voz clonada sintetiza em ~4x o tempo do áudio,
    # e o DONE só sai quando o último pedaço virou som
    done = await s.wait_for("state", mark, state="DONE", timeout=180)
    final = s.seen("stt_final", mark)

    print(f"   transcrição: {final and final['text']!r}")
    print(f"   falou      : {speak and speak['text']!r}")
    if speak:
        print(f"   1º áudio em {(speak['_t'] - t0):.1f}s do início da fala")
    await s.wait_for("state", mark, state="IDLE", timeout=180)
    ok = bool(speak and done)
    print("   " + ("OK" if ok else "FALHOU: não respondeu"))
    return ok


async def main():
    desde = time.time()
    async with websockets.connect(URL, max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "device_type": "web",
                                  "network": "wifi-home"}))
        s = Session(ws)
        await asyncio.sleep(1.0)

        resultados = []
        for frase, esperado in CENARIOS:
            resultados.append(await roda(s, frase, esperado))
            await asyncio.sleep(2)
        s.task.cancel()

    print("\n== registro (áudio + decisão) ==")
    regs = registros_recentes(desde)
    for r in regs:
        rota = json.loads(r["rota"] or "{}")
        wav = DATA / (r["audio_path"] or "")
        tamanho = wav.stat().st_size // 1024 if r["audio_path"] and wav.exists() else 0
        print(f"   {r['transcricao'][:34]!r:38s} agente={r['agente']:9s} "
              f"audio={tamanho}KB rota={rota.get('motivo') or '-'}")

    esperados = len(CENARIOS)
    com_audio = sum(1 for r in regs
                    if r["audio_path"] and (DATA / r["audio_path"]).exists())
    print(f"\n   registros gravados: {len(regs)}/{esperados}")
    print(f"   com áudio no disco: {com_audio}/{esperados}")

    ok = all(resultados) and len(regs) >= esperados and com_audio >= esperados
    print("\n" + ("=== TUDO OK ===" if ok else "=== FALHOU ==="))
    sys.exit(0 if ok else 1)


asyncio.run(main())
