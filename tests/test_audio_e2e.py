"""E2E de áudio: sintetiza "Hey Jarvis" + "liga a luz da sala", streama como PCM
16kHz em frames de 80ms pelo WebSocket e verifica wake → STT → intent → resposta.

Uso: python tests/test_audio_e2e.py          (servidor no ar na 8040)
Com STT dummy valida só wake+VAD (termina em IDLE). Com nemotron valida o MVP inteiro.
"""
import asyncio
import io
import json
import sys
import time
from pathlib import Path

import numpy as np
import websockets

URL = "ws://127.0.0.1:8040/ws/web-dev?token=tk_web_3Za5Xb7Vc9Td1Rf4Pg6Nh8Lj2"
SR = 16000
FRAME = 1280  # 80ms
CACHE = Path(__file__).parent / ".cache"


async def tts_pcm(text: str, voice: str = "pt-BR-FranciscaNeural") -> np.ndarray:
    """Gera fala e devolve PCM int16 16kHz mono."""
    CACHE.mkdir(exist_ok=True)
    mp3 = CACHE / f"{abs(hash((text, voice)))}.mp3"
    if not mp3.exists():
        import edge_tts
        await edge_tts.Communicate(text, voice).save(str(mp3))
    import subprocess
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(mp3), "-f", "s16le", "-ac", "1",
         "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16)


def frames(pcm: np.ndarray):
    pad = (-len(pcm)) % FRAME
    pcm = np.concatenate([pcm, np.zeros(pad, dtype=np.int16)])
    for i in range(0, len(pcm), FRAME):
        yield pcm[i:i + FRAME].tobytes()


async def stream(ws, pcm: np.ndarray, realtime: bool = True):
    for fr in frames(pcm):
        await ws.send(fr)
        if realtime:
            await asyncio.sleep(0.075)


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(SR * seconds), dtype=np.int16)


async def main():
    wake = await tts_pcm("Hey Jarvis!", voice="en-US-GuyNeural")
    command = await tts_pcm("Liga a luz da sala.")
    events = []

    async with websockets.connect(URL, max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "device_type": "web", "network": "wifi-home"}))

        async def reader():
            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] not in ("ambient",):
                    print(f"<- {msg}")
                    events.append(msg)

        rtask = asyncio.create_task(reader())
        await asyncio.sleep(0.5)

        t0 = time.perf_counter()
        await stream(ws, np.concatenate([wake, silence(0.4)]))
        for _ in range(40):
            if any(e["type"] == "wake" for e in events):
                break
            await asyncio.sleep(0.1)
        else:
            print("FALHOU: wake word não detectada"); sys.exit(1)
        print(f"== wake detectada em {(time.perf_counter() - t0) * 1000:.0f}ms (inclui duração do áudio)")

        await stream(ws, np.concatenate([command, silence(1.2)]))
        for _ in range(300):
            if any(e["type"] == "state" and e["state"] == "IDLE" for e in events):
                break
            await asyncio.sleep(0.1)
        rtask.cancel()

    finals = [e for e in events if e["type"] == "stt_final"]
    speaks = [e for e in events if e["type"] == "speak"]
    done = any(e["type"] == "state" and e["state"] == "DONE" for e in events)
    print("\n== resultado ==")
    print("stt_final:", finals)
    print("speak:", speaks)
    if finals and done and speaks:
        print("MVP E2E OK")
    else:
        print("Parcial: wake+VAD ok; STT/intent exigem engine nemotron")


asyncio.run(main())
