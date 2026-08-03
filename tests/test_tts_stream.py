"""Mede o ganho do TTS em streaming: quanto tempo até o JARVIS COMEÇAR a falar.

Faz uma pergunta que exige o LLM (não é comando local) e cronometra:
  - quando chega o primeiro pedaço de áudio (é o que importa pra sensação)
  - quando chega o último
Compara com o tamanho total da resposta.

Uso: python tests/test_tts_stream.py ["pergunta"]   (servidor no ar)
"""
import asyncio
import json
import sys
import time

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conexao import ws_url  # noqa: E402

URL = ws_url()
PERGUNTA = sys.argv[1] if len(sys.argv) > 1 else \
    "me explica em duas frases o que e um buraco negro"


async def main():
    async with websockets.connect(URL, max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "device_type": "web",
                                  "network": "wifi-home"}))
        await asyncio.sleep(0.5)

        # pedido escrito: testa o caminho do agente sem depender de microfone
        await ws.send(json.dumps({"type": "texto", "text": PERGUNTA}))

        t0 = time.perf_counter()
        primeiro = None
        pedacos = []
        print(f"pergunta: {PERGUNTA!r}\n")
        while True:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=90))
            except asyncio.TimeoutError:
                break
            t = time.perf_counter() - t0
            if msg["type"] == "speak":
                if primeiro is None:
                    primeiro = t
                pedacos.append((t, msg.get("text", "")))
                print(f"  [{t:5.1f}s] pedaço {msg.get('seq', '-')}: {msg.get('text')!r}")
            elif msg["type"] == "speak_end":
                print(f"  [{t:5.1f}s] fim da resposta")
                break
            elif msg["type"] == "state" and msg["state"] in ("ERROR",):
                print("  erro no servidor")
                break

    if not pedacos:
        print("\nFALHOU: nenhuma fala recebida")
        return 1
    total = " ".join(p[1] for p in pedacos)
    ultimo = pedacos[-1][0]
    print(f"\ncomeçou a falar em : {primeiro:.1f}s")
    print(f"terminou de gerar  : {ultimo:.1f}s")
    print(f"pedaços            : {len(pedacos)}")
    print(f"resposta ({len(total.split())} palavras): {total!r}")
    if len(pedacos) > 1:
        print(f"\nsem streaming, o áudio só começaria em ~{ultimo:.1f}s "
              f"(ganho de {ultimo - primeiro:.1f}s)")
    return 0


sys.exit(asyncio.run(main()))
