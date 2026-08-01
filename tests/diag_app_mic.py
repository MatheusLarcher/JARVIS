"""Diagnóstico: o que o app de bandeja está usando de microfone AGORA.

Uso: python tests/diag_app_mic.py     (app com --remote-debugging-port=9333)
"""
import asyncio
import json

import httpx
import websockets

CDP = "http://127.0.0.1:9333"


async def evaluate(ws, expr, msg_id=1):
    await ws.send(json.dumps({
        "id": msg_id, "method": "Runtime.evaluate",
        "params": {"expression": expr, "awaitPromise": True, "returnByValue": True},
    }))
    while True:
        r = json.loads(await ws.recv())
        if r.get("id") == msg_id:
            out = r.get("result", {})
            if "exceptionDetails" in out:
                return {"erro": str(out["exceptionDetails"])[:300]}
            return out.get("result", {}).get("value")


async def main():
    async with httpx.AsyncClient() as c:
        pages = (await c.get(f"{CDP}/json")).json()
    ws_url = next(p["webSocketDebuggerUrl"] for p in pages if p.get("type") == "page")

    async with websockets.connect(ws_url, max_size=None) as ws:
        diag = await evaluate(ws, "window.__jarvisDiag ? window.__jarvisDiag() : 'sem diagnostico'")
        print("=== estado interno do app ===")
        if isinstance(diag, dict):
            print(f"  microfone em uso : {diag.get('label')}")
            print(f"  frames enviados  : {diag.get('frames')}")
            print(f"  pico de nível    : {diag.get('peak')}")
            print(f"  sem sinal há     : {diag.get('semSinalHa')}s")
            print(f"  online / estado  : {diag.get('online')} / {diag.get('state')}")
            print(f"  prefs            : {json.dumps(diag.get('prefs'))}")
            if diag.get("error"):
                print(f"  ERRO             : {diag['error']}")
        else:
            print(" ", diag)


asyncio.run(main())
