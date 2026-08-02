"""Cronometra CADA ETAPA do JARVIS, do "Jarvis" até o áudio da resposta.

Roda os dois caminhos:
  A) comando local  ("Jarvis, liga a luz da sala")  -> não passa pelo LLM
  B) pergunta       ("Jarvis, quem foi Santos Dumont") -> passa pelo LLM

Mede pelo lado do cliente (o que você sente) e cruza com a telemetria do
servidor (o que cada peça gastou).

Uso: python tests/bench_pipeline.py [repeticoes]     (servidor no ar)
"""
import asyncio
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import websockets

URL = "ws://127.0.0.1:8040/ws/web-dev?token=tk_web_3Za5Xb7Vc9Td1Rf4Pg6Nh8Lj2"
SERVER = "http://127.0.0.1:8040"
CACHE = Path(__file__).parent / ".cache"
SR, FRAME = 16000, 1280
REPETICOES = int(sys.argv[1]) if len(sys.argv) > 1 else 3

CASOS = [
    ("comando local", "Jarvis, liga a luz da sala."),
    ("pergunta ao LLM", "Jarvis, quem foi Santos Dumont?"),
]


async def tts_pcm(texto: str) -> np.ndarray:
    import edge_tts
    CACHE.mkdir(exist_ok=True)
    mp3 = CACHE / f"pipe_{abs(hash(texto))}.mp3"
    if not mp3.exists():
        await edge_tts.Communicate(texto, "pt-BR-AntonioNeural").save(str(mp3))
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp3), "-f", "s16le",
                          "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16)


async def uma_rodada(frase: str) -> dict | None:
    audio = await tts_pcm(frase)
    silencio = np.zeros(int(SR * 1.2), dtype=np.int16)
    pcm = np.concatenate([audio, silencio])
    dur_fala = len(audio) / SR

    marcos = {}
    async with websockets.connect(URL, max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "device_type": "web",
                                  "network": "wifi-home"}))
        await asyncio.sleep(0.4)

        eventos = []

        async def ler():
            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] != "ambient":
                    msg["_t"] = time.perf_counter()
                    eventos.append(msg)

        tarefa = asyncio.create_task(ler())
        t0 = time.perf_counter()
        pad = (-len(pcm)) % FRAME
        cheio = np.concatenate([pcm, np.zeros(pad, dtype=np.int16)])
        for i in range(0, len(cheio), FRAME):
            await ws.send(cheio[i:i + FRAME].tobytes())
            await asyncio.sleep(0.075)

        # espera a resposta terminar
        limite = time.perf_counter() + 60
        while time.perf_counter() < limite:
            if any(e["type"] == "speak" for e in eventos) and \
               any(e["type"] == "state" and e["state"] in ("DONE", "ERROR")
                   for e in eventos):
                break
            await asyncio.sleep(0.1)
        tarefa.cancel()

    def quando(tipo, **campos):
        for e in eventos:
            if e["type"] == tipo and all(e.get(k) == v for k, v in campos.items()):
                return e["_t"] - t0
        return None

    marcos["fim da fala"] = dur_fala
    marcos["reator acende"] = quando("wake")
    marcos["1ª parcial"] = quando("stt_partial")
    marcos["transcrição final"] = quando("stt_final")
    marcos["1º áudio da resposta"] = quando("speak")
    marcos["concluído"] = quando("state", state="DONE") or quando("state", state="ERROR")
    marcos["_transcricao"] = next(
        (e["text"] for e in eventos if e["type"] == "stt_final"), "")
    marcos["_resposta"] = " ".join(
        e.get("text", "") for e in eventos if e["type"] == "speak")
    return marcos


async def main():
    print(f"{REPETICOES} rodadas por caso; tempos contados do início da fala\n")
    async with httpx.AsyncClient() as c:
        antes = (await c.get(f"{SERVER}/api/metrics/recent?limit=1")).json()
    ultimo_ts = antes[0]["ts"] if antes else 0

    for nome, frase in CASOS:
        print(f"=== {nome}: {frase!r} ===")
        colunas = ["reator acende", "1ª parcial", "transcrição final",
                   "1º áudio da resposta", "concluído"]
        acumulado = {c: [] for c in colunas}
        exemplo = None
        for i in range(REPETICOES):
            m = await uma_rodada(frase)
            exemplo = m
            for c in colunas:
                if m.get(c) is not None:
                    acumulado[c].append(m[c])
            await asyncio.sleep(1.5)

        print(f"  fala dura {exemplo['fim da fala']:.2f}s | "
              f"ouviu: {exemplo['_transcricao']!r}")
        print(f"  respondeu: {exemplo['_resposta'][:90]!r}\n")
        print(f"  {'etapa':24s} {'mediana':>9s} {'melhor':>8s} {'pior':>8s}")
        anterior = 0.0
        for c in colunas:
            vals = acumulado[c]
            if not vals:
                print(f"  {c:24s} {'—':>9s}")
                continue
            med = statistics.median(vals)
            print(f"  {c:24s} {med:>8.2f}s {min(vals):>7.2f}s {max(vals):>7.2f}s"
                  f"   (+{med - anterior:.2f}s)")
            anterior = med
        print()

    # o que o servidor registrou por dentro
    async with httpx.AsyncClient() as c:
        rows = (await c.get(f"{SERVER}/api/metrics/recent?limit=20")).json()
    novos = [r for r in rows if r["ts"] > ultimo_ts]
    if novos:
        print("=== por dentro do servidor (ms desde o wake) ===")
        for r in novos[:4]:
            m = json.loads(r["metrics"])
            print(f"  {r['transcript'][:40]!r:44s} {r['handler']}")
            print("   ", {k: v for k, v in m.items()})


asyncio.run(main())
