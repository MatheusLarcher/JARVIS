"""O áudio de confirmação ("Sim?") que o aparelho recebe é o ATUAL?

Trocar a voz não muda o nome do arquivo, então o aparelho podia continuar
tocando o áudio antigo guardado em cache. Este teste confere que a URL leva a
versão do arquivo e que o servidor não manda cachear.

Uso: python tests/test_ack_atualizado.py     (servidor no ar)
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
URL = "ws://127.0.0.1:8040/ws/web-dev?token=tk_web_3Za5Xb7Vc9Td1Rf4Pg6Nh8Lj2"
SERVER = "http://127.0.0.1:8040"


async def main():
    falhas = []

    async with websockets.connect(URL, max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "device_type": "web"}))
        acks = None
        for _ in range(20):
            msg = json.loads(await asyncio.wait_for(ws.recv(), 10))
            if msg["type"] == "hello_ok":
                acks = msg["ack_sounds"]
                break
    if not acks:
        print("FALHOU: servidor não mandou os áudios de confirmação")
        return 1

    print(f"{len(acks)} áudios de confirmação:")
    for a in acks:
        print(f"  {a['url']}")

    if not all("?v=" in a["url"] for a in acks):
        falhas.append("URL sem versão (o aparelho vai continuar com o áudio antigo)")

    async with httpx.AsyncClient() as c:
        r = await c.get(SERVER + acks[0]["url"])
        if r.status_code != 200:
            falhas.append(f"não consegui baixar o áudio ({r.status_code})")
        cache = r.headers.get("cache-control", "")
        if "no-store" not in cache:
            falhas.append(f"servidor mandou cachear (Cache-Control: {cache!r})")

        # o que o aparelho baixa tem que ser byte a byte o arquivo em disco
        nome = acks[0]["name"]
        local = ROOT / "server" / "data" / "library" / "acknowledgement" / nome
        if local.exists() and r.content != local.read_bytes():
            falhas.append("o áudio baixado é diferente do que está no disco")

    print()
    if falhas:
        for f in falhas:
            print("FALHA:", f)
        return 1
    print("OK: o aparelho recebe sempre o áudio atual")
    return 0


sys.exit(asyncio.run(main()))
