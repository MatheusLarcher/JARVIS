"""Tira um print da janela do PC (para conferir o visual).

Uso: python tests/shot_janela.py [saida.png]   (app com --remote-debugging-port=9333)
"""
import asyncio
import base64
import json
import sys
from pathlib import Path

import httpx
import websockets

CDP = "http://127.0.0.1:9333"
SAIDA = Path(sys.argv[1] if len(sys.argv) > 1 else "janela.png")


async def main():
    async with httpx.AsyncClient() as c:
        alvos = (await c.get(f"{CDP}/json")).json()
    pagina = next(p for p in alvos if p.get("type") == "page")
    async with websockets.connect(pagina["webSocketDebuggerUrl"], max_size=None) as ws:
        # mostra a janela e destaca os controles (hover) pro print
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
            "expression": "window.jarvisDesktop.pin(true); "
                          "document.querySelectorAll('.win-close,.gear')"
                          ".forEach(e => e.style.opacity = 1)"}}))
        await asyncio.sleep(1.2)
        await ws.send(json.dumps({"id": 2, "method": "Page.captureScreenshot",
                                  "params": {"format": "png"}}))
        while True:
            r = json.loads(await ws.recv())
            if r.get("id") == 2:
                SAIDA.write_bytes(base64.b64decode(r["result"]["data"]))
                print(f"print salvo em {SAIDA}")
                break
        await ws.send(json.dumps({"id": 3, "method": "Runtime.evaluate", "params": {
            "expression": "window.jarvisDesktop.pin(false)"}}))
        await asyncio.sleep(0.3)


asyncio.run(main())
