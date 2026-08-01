"""Diagnóstico: descobre qual microfone realmente escuta o ambiente.

Toca uma frase pelo alto-falante (via app de bandeja, com --remote-debugging-port=9333)
e grava simultaneamente de cada microfone, medindo o volume captado.

Uso: python tests/diag_microfones.py
"""
import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "server" / "data" / "tts_cache"
SERVER = "http://127.0.0.1:8040"
CDP = "http://127.0.0.1:9333"
REC_S = 7


def list_mics() -> list[str]:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-list_devices", "true",
                          "-f", "dshow", "-i", "dummy"],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace").stderr
    mics = []
    for line in out.splitlines():
        m = re.search(r'"([^"]+)"\s*\(audio\)', line)
        if m:
            mics.append(m.group(1))
    return mics


def record_level(mic: str, seconds: int) -> tuple[float, float]:
    """Grava e devolve (volume médio dB, pico dB). -91 dB = silêncio absoluto."""
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-f", "dshow", "-audio_buffer_size", "80",
         "-i", f"audio={mic}", "-t", str(seconds), "-af", "volumedetect",
         "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    mean = re.search(r"mean_volume:\s*(-?[\d.]+) dB", p.stderr)
    peak = re.search(r"max_volume:\s*(-?[\d.]+) dB", p.stderr)
    if not mean:
        return (-999.0, -999.0)
    return (float(mean.group(1)), float(peak.group(1)))


async def play_through_speaker():
    """Usa o app de bandeja pra tocar no alto-falante embutido."""
    import edge_tts
    name = "teste_mic.mp3"
    await edge_tts.Communicate("Jarvis, liga a luz da sala.",
                               "pt-BR-AntonioNeural").save(str(CACHE / name))
    url = f"{SERVER}/audio/tts/{name}"

    async with httpx.AsyncClient() as c:
        pages = (await c.get(f"{CDP}/json")).json()
    ws_url = next(p["webSocketDebuggerUrl"] for p in pages if p.get("type") == "page")

    async with websockets.connect(ws_url, max_size=None) as ws:
        expr = f"""
            (async () => {{
                const devs = (await navigator.mediaDevices.enumerateDevices())
                    .filter(d => d.kind === 'audiooutput');
                const sp = devs.find(d => /alto-falante|speaker|realtek/i.test(d.label)
                                          && d.deviceId !== 'communications') || devs[0];
                const a = new Audio({json.dumps(url)});
                a.volume = 1.0;
                if (a.setSinkId) await a.setSinkId(sp.deviceId);
                await a.play();
                await new Promise(r => a.onended = r);
                return sp.label;
            }})()
        """
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                  "params": {"expression": expr, "awaitPromise": True,
                                             "returnByValue": True}}))
        while True:
            r = json.loads(await ws.recv())
            if r.get("id") == 1:
                return r.get("result", {}).get("result", {}).get("value")


async def main():
    mics = list_mics()
    print("microfones encontrados:")
    for m in mics:
        print(f"  - {m}")

    print(f"\nmedindo cada microfone enquanto toco a frase no alto-falante "
          f"({REC_S}s cada)...\n")
    print(f"{'microfone':55s} {'médio':>8s} {'pico':>8s}   avaliação")
    results = []
    for mic in mics:
        play = asyncio.create_task(play_through_speaker())
        loop = asyncio.get_running_loop()
        level = await loop.run_in_executor(None, record_level, mic, REC_S)
        try:
            await asyncio.wait_for(play, timeout=5)
        except Exception:
            pass
        mean, peak = level
        if mean == -999:
            verdict = "NAO ABRIU (em uso por outro app?)"
        elif peak < -50:
            verdict = "mudo"
        elif peak < -25:
            verdict = "capta pouco"
        else:
            verdict = "OUVE BEM"
        results.append((mic, mean, peak, verdict))
        print(f"{mic:55s} {mean:8.1f} {peak:8.1f}   {verdict}")

    bons = [r for r in results if r[3] == "OUVE BEM"]
    print("\n" + ("melhor microfone: " + bons[0][0] if bons
                  else "NENHUM microfone captou o som do alto-falante"))


asyncio.run(main())
