"""A primeira pergunta difícil do dia sai rápida no servidor de verdade?

Manda pedidos pelo WebSocket e lê os tempos que o próprio servidor gravou no
registro. Interessa o intervalo `roteador_ms -> llm_first_token_ms`: é quanto o
agente demorou pra começar a responder depois da rota escolhida.

Rode logo depois de reiniciar o servidor, pra pegar a PRIMEIRA chamada.
Uso: python tests/bench_nuvem_no_servidor.py
"""
import asyncio
import json
import sqlite3
import sys
import time
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conexao import ws_url  # noqa: E402

WS = ws_url()
DB = Path(__file__).resolve().parents[1] / "server" / "data" / "jarvis.db"

# frases coladas nos exemplos do agente `avancado` (settings.yml) pra ele ser
# escolhido de verdade — o roteador é um modelo pequeno e varia
PEDIDOS = [
    "compara duas opcoes de energia e me diz qual e melhor pra uma casa",
    "compara duas opcoes de carro e me diz qual e melhor pra cidade",
    "compara duas opcoes de internet e me diz qual e melhor pra trabalhar",
]


def registros(desde: float) -> list[dict]:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        cur = con.execute("SELECT transcricao, agente, metricas_json FROM registros "
                          "WHERE ts > ? ORDER BY id", (desde,))
        return [{"t": r[0], "agente": r[1], "m": json.loads(r[2] or "{}")}
                for r in cur.fetchall()]
    finally:
        con.close()


async def main():
    desde = time.time()
    async with websockets.connect(WS, max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "device_type": "web"}))
        eventos = []

        async def ler():
            async for raw in ws:
                m = json.loads(raw)
                if m["type"] != "ambient":
                    eventos.append(m)
        tarefa = asyncio.create_task(ler())
        await asyncio.sleep(0.8)

        for i, pedido in enumerate(PEDIDOS):
            marca = len(eventos)
            await ws.send(json.dumps({"type": "texto", "text": pedido}))
            t0 = time.monotonic()
            while time.monotonic() - t0 < 180:
                if any(e["type"] == "state" and e.get("state") == "IDLE"
                       for e in eventos[marca:]):
                    break
                await asyncio.sleep(0.2)
            print(f"   pedido {i + 1} respondido")
            await asyncio.sleep(1.5)
        tarefa.cancel()

    print("\nagente escolhido e tempo até a 1a palavra (do fim da rota):\n")
    nuvem = []
    for r in registros(desde):
        m = r["m"]
        rota = m.get("roteador_ms")
        primeiro = m.get("llm_first_token_ms")
        if rota and primeiro:
            dt = (primeiro - rota) / 1000
            marca = " <- NUVEM" if r["agente"] == "avancado" else ""
            print(f"   {r['agente']:9s} {dt:5.2f}s{marca}")
            if r["agente"] == "avancado":
                nuvem.append(dt)

    if not nuvem:
        print("\n   (o roteador não mandou nada pra nuvem desta vez — rode de novo)")
        return 1
    print(f"\n   nuvem: 1a chamada {nuvem[0]:.2f}s" +
          (f" | seguintes {min(nuvem[1:]):.2f}s" if len(nuvem) > 1 else ""))
    ok = nuvem[0] < 3.0
    print("   " + ("OK: a primeira já sai rápida (aquecimento funcionando)"
                   if ok else "LENTA: parece que a nuvem não foi aquecida"))
    return 0 if ok else 1


sys.exit(asyncio.run(main()))
