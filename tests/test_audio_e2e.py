"""E2E de áudio: sintetiza fala, streama como PCM 16kHz em frames de 80ms pelo
WebSocket e confere o fluxo inteiro (wake → STT → intent → resposta falada).

Cenários:
  1) frase única: "Jarvis, liga a luz da sala"   → NÃO deve tocar ack, executa direto
  2) duas etapas: "Jarvis"  →  ack  →  "liga a luz da sala"

Uso: python tests/test_audio_e2e.py [1|2]     (servidor no ar na 8040)
"""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conexao import ws_url  # noqa: E402

URL = ws_url()
SR = 16000
FRAME = 1280  # 80ms
CACHE = Path(__file__).parent / ".cache"
VOICE = "pt-BR-FranciscaNeural"


async def tts_pcm(text: str, voice: str = VOICE) -> np.ndarray:
    """Gera fala e devolve PCM int16 16kHz mono."""
    CACHE.mkdir(exist_ok=True)
    mp3 = CACHE / f"{abs(hash((text, voice)))}.mp3"
    if not mp3.exists():
        import edge_tts
        await edge_tts.Communicate(text, voice).save(str(mp3))
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(mp3), "-f", "s16le", "-ac", "1",
         "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16)


def frames(pcm: np.ndarray):
    pad = (-len(pcm)) % FRAME
    pcm = np.concatenate([pcm, np.zeros(pad, dtype=np.int16)])
    for i in range(0, len(pcm), FRAME):
        yield pcm[i:i + FRAME].tobytes()


async def stream(ws, pcm: np.ndarray):
    for fr in frames(pcm):
        await ws.send(fr)
        await asyncio.sleep(0.075)     # tempo real


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(SR * seconds), dtype=np.int16)


class Session:
    """Conexão + coleta de eventos, com espera por evento específico."""

    def __init__(self, ws):
        self.ws = ws
        self.events = []
        self.task = asyncio.create_task(self._reader())

    async def _reader(self):
        async for raw in self.ws:
            msg = json.loads(raw)
            if msg["type"] != "ambient":
                msg["_t"] = time.perf_counter()      # pra medir latência real
                print(f"   <- { {k: v for k, v in msg.items() if k != '_t'} }")
                self.events.append(msg)

    def seen(self, type_, since=0, **fields):
        for e in self.events[since:]:
            if e["type"] == type_ and all(e.get(k) == v for k, v in fields.items()):
                return e
        return None

    async def wait_for(self, type_, since=0, timeout=45, **fields):
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            hit = self.seen(type_, since, **fields)
            if hit:
                return hit
            await asyncio.sleep(0.1)
        return None


async def scenario_single(s: Session):
    """Tudo numa frase só — o comando vai junto com o nome."""
    print("\n== cenário 1: 'Jarvis, liga a luz da sala' (frase única) ==")
    audio = await tts_pcm("Jarvis, liga a luz da sala.")
    mark = len(s.events)
    t0 = time.perf_counter()
    await stream(s.ws, np.concatenate([audio, silence(1.5)]))

    wake = await s.wait_for("wake", mark)
    if not wake:
        print("FALHOU: não reconheceu a chamada"); return False
    # o "Jarvis" está no comecinho do áudio, então isso é ~o tempo de reação real
    print(f"   reator acendeu {(wake['_t'] - t0) * 1000:.0f}ms depois de começar a falar")

    speak = await s.wait_for("speak", mark)
    done = await s.wait_for("state", mark, state="DONE")
    final = s.seen("stt_final", mark)
    acked = s.seen("ack", mark)

    print(f"\n   transcrição: {final and final['text']!r}")
    print(f"   resposta   : {speak and speak['text']!r}")
    print(f"   tocou 'Sim?' antes? {'SIM (não devia)' if acked else 'não (correto)'}")
    ok = bool(speak and done and not acked)
    print("   " + ("OK: comando na mesma frase funcionou" if ok else "FALHOU"))
    await s.wait_for("state", mark, state="IDLE")
    return ok


async def scenario_two_step(s: Session):
    """Chama, ouve o 'Sim?', depois manda o comando."""
    print("\n== cenário 2: 'Jarvis' → ack → 'liga a luz da sala' ==")
    call = await tts_pcm("Jarvis?")
    cmd = await tts_pcm("Liga a luz da sala.")
    mark = len(s.events)
    await stream(s.ws, np.concatenate([call, silence(1.5)]))

    if not await s.wait_for("wake", mark):
        print("FALHOU: não reconheceu a chamada"); return False
    if not await s.wait_for("ack", mark):
        print("FALHOU: não tocou o áudio de confirmação"); return False
    print("   tocou o 'Sim?' e ficou ouvindo")

    mark2 = len(s.events)
    await stream(s.ws, np.concatenate([cmd, silence(1.5)]))
    speak = await s.wait_for("speak", mark2)
    done = await s.wait_for("state", mark2, state="DONE")
    final = s.seen("stt_final", mark2)
    print(f"\n   transcrição: {final and final['text']!r}")
    print(f"   resposta   : {speak and speak['text']!r}")
    ok = bool(speak and done)
    print("   " + ("OK: fluxo em duas etapas funcionou" if ok else "FALHOU"))
    await s.wait_for("state", mark2, state="IDLE")
    return ok


async def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    async with websockets.connect(URL, max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "device_type": "web",
                                  "network": "wifi-home"}))
        s = Session(ws)
        await asyncio.sleep(1.0)

        results = []
        if which in ("1", "all"):
            results.append(await scenario_single(s))
        if which in ("2", "all"):
            await asyncio.sleep(2)
            results.append(await scenario_two_step(s))
        s.task.cancel()

    print("\n" + ("=== TUDO OK ===" if all(results) else "=== FALHOU ==="))
    sys.exit(0 if all(results) else 1)


# guarda: outros testes importam as funções daqui (tts_pcm, stream, Session) e
# sem isto o arquivo inteiro rodava junto
if __name__ == "__main__":
    asyncio.run(main())
