"""Teste ACÚSTICO: toca a frase pelo alto-falante e confere se o microfone do PC
acionou o JARVIS de verdade (mic real → wake → comando → resposta).

Precisa do app de bandeja rodando com a porta de debug:
    npx electron . --remote-debugging-port=9333

Uso: python tests/test_mic_real.py ["Jarvis, liga a luz da sala."]
"""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "server" / "data" / "tts_cache"
SERVER = "http://127.0.0.1:8040"
CDP = "http://127.0.0.1:9333"
PHRASE = sys.argv[1] if len(sys.argv) > 1 else "Jarvis, liga a luz da sala."


async def make_audio() -> str:
    """Gera a frase e deixa acessível pela URL do servidor."""
    import edge_tts
    name = "teste_mic.mp3"
    out = CACHE / name
    await edge_tts.Communicate(PHRASE, "pt-BR-AntonioNeural").save(str(out))
    return f"{SERVER}/audio/tts/{name}"


async def cdp_page_ws() -> str:
    async with httpx.AsyncClient() as c:
        pages = (await c.get(f"{CDP}/json")).json()
    for p in pages:
        if p.get("type") == "page":
            return p["webSocketDebuggerUrl"]
    raise RuntimeError("nenhuma página encontrada no CDP (o app está com --remote-debugging-port?)")


async def evaluate(ws, expr, msg_id):
    await ws.send(json.dumps({
        "id": msg_id, "method": "Runtime.evaluate",
        "params": {"expression": expr, "awaitPromise": True, "returnByValue": True},
    }))
    while True:
        r = json.loads(await ws.recv())
        if r.get("id") == msg_id:
            res = r.get("result", {}).get("result", {})
            if "exceptionDetails" in r.get("result", {}):
                raise RuntimeError(r["result"]["exceptionDetails"])
            return res.get("value")


async def main():
    url = await make_audio()
    print(f"frase: {PHRASE!r}")

    ws_url = await cdp_page_ws()
    async with websockets.connect(ws_url, max_size=None) as ws:
        devices = await evaluate(ws, """
            (async () => (await navigator.mediaDevices.enumerateDevices())
                .filter(d => d.kind === 'audiooutput')
                .map(d => ({id: d.deviceId, label: d.label})))()
        """, 1)
        print("\nsaídas de áudio disponíveis:")
        for d in devices:
            print(f"  - {d['label']}")

        # prefere o alto-falante embutido: é o que o microfone do notebook escuta
        speaker = next((d for d in devices
                        if any(k in d["label"].lower()
                               for k in ("alto-falante", "speaker", "realtek"))), None)
        if not speaker:
            speaker = next((d for d in devices if d["id"] == "default"), devices[0])
        print(f"\ntocando em: {speaker['label']}")

        before = (await httpx.AsyncClient().get(
            f"{SERVER}/api/metrics/recent?limit=1")).json()
        last_before = before[0]["ts"] if before else 0

        await evaluate(ws, f"""
            (async () => {{
                const a = new Audio({json.dumps(url)});
                a.volume = 1.0;
                if (a.setSinkId) await a.setSinkId({json.dumps(speaker['id'])});
                await a.play();
                await new Promise(r => a.onended = r);
                return 'tocou';
            }})()
        """, 2)
        print("áudio reproduzido; esperando o JARVIS reagir...")

    t0 = time.monotonic()
    async with httpx.AsyncClient() as c:
        while time.monotonic() - t0 < 40:
            rows = (await c.get(f"{SERVER}/api/metrics/recent?limit=3")).json()
            novo = [r for r in rows if r["ts"] > last_before]
            if novo:
                r = novo[0]
                print(f"\n>>> O JARVIS OUVIU: {r['transcript']!r}")
                print(f"    intent   : {r['intent']}")
                print(f"    device   : {r['device_id']}")
                print(f"    métricas : {r['metrics']}")
                print("\nOK: microfone real funcionando")
                return 0
            await asyncio.sleep(1)

    print("\nFALHOU: o microfone não captou (nenhuma interação registrada)")
    return 1


sys.exit(asyncio.run(main()))
