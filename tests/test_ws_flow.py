"""Teste de integração do gateway: conecta como device, manda hello + texto simulado.

Uso: python tests/test_ws_flow.py  (servidor precisa estar no ar na 8040)
Simula o fluxo sem microfone: injeta a transcrição via pipeline de texto? Não —
valida hello/auth/ambient e o endpoint REST. O fluxo de áudio real é testado
por tests/test_audio_e2e.py com wav sintético.
"""
import asyncio
import json
import sys
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conexao import ws_url  # noqa: E402

URL = ws_url()
async def main():
    async with websockets.connect(URL) as ws:
        await ws.send(json.dumps({"type": "hello", "device_type": "web", "network": "wifi-home"}))
        for _ in range(3):
            msg = json.loads(await asyncio.wait_for(ws.recv(), 10))
            print("<-", msg)
            if msg["type"] == "hello_ok":
                assert msg["context"]["device_id"] == "web-dev"
                assert msg["ack_sounds"], "ack_sounds vazio"
        await ws.send(json.dumps({"type": "ping", "ts": 1}))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
            print("<-", msg)
            if msg["type"] == "pong":
                break
    print("OK: hello/auth/ack_sounds/ping")

    # auth inválida deve ser rejeitada (HTTP 403 no handshake)
    try:
        async with websockets.connect("ws://127.0.0.1:8040/ws/web-dev?token=errado") as ws:
            await ws.recv()
        print("FALHOU: aceitou token inválido")
        sys.exit(1)
    except (websockets.exceptions.InvalidStatus, websockets.exceptions.ConnectionClosedError):
        print("OK: token inválido rejeitado")


asyncio.run(main())
