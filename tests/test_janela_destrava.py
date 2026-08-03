"""A janela do PC destrava depois de uma resposta pronta da biblioteca.

O device liga o "estou falando" no `speak` de seq 0 e só desliga no `speak_end`.
Como o caminho da biblioteca ("Pronto.", "Bom dia.") não mandava `speak_end`,
`falando` ficava true pra sempre: a janela não voltava a ficar translúcida nem
se recolhia — justamente nos comandos mais usados.

Aqui a interação acontece de VERDADE (áudio pelo WebSocket) e a gente lê o
estado interno do app de bandeja pelo CDP.

Uso:
  1) feche o JARVIS da bandeja e abra com:
       npx electron . --remote-debugging-port=9333    (em apps/desktop)
     ou rode o EXE instalado com o mesmo parâmetro
  2) python tests/test_janela_destrava.py
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx
import numpy as np
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent))

from conexao import ws_url  # noqa: E402
from test_audio_e2e import Session, silence, stream, tts_pcm  # noqa: E402

CDP = "http://127.0.0.1:9333"
WS = ws_url()
async def _cdp():
    async with httpx.AsyncClient() as c:
        alvos = (await c.get(f"{CDP}/json")).json()
    pagina = next(p for p in alvos if p.get("type") == "page")
    return await websockets.connect(pagina["webSocketDebuggerUrl"], max_size=None)


async def _eval(ws, expr, i=[0], promessa=False):
    i[0] += 1
    await ws.send(json.dumps({"id": i[0], "method": "Runtime.evaluate",
                              "params": {"expression": expr, "returnByValue": True,
                                         "awaitPromise": promessa}}))
    while True:
        r = json.loads(await ws.recv())
        if r.get("id") == i[0]:
            return r.get("result", {}).get("result", {}).get("value")


async def info(cdp):
    return await _eval(cdp, "window.jarvisDesktop.windowInfo()", promessa=True)


async def espera_destravar(cdp, limite=25.0):
    """Espera o app parar de se achar 'falando'."""
    t = 0.0
    while t < limite:
        i = await info(cdp)
        if not i["falando"] and not i["processando"]:
            return i
        await asyncio.sleep(0.5)
        t += 0.5
    return await info(cdp)


async def frase(s: Session, texto: str):
    audio = await tts_pcm(texto)
    mark = len(s.events)
    await stream(s.ws, np.concatenate([audio, silence(1.5)]))
    await s.wait_for("state", mark, state="IDLE", timeout=120)


async def main():
    try:
        cdp = await _cdp()
    except Exception as e:
        print(f"não achei o app na porta de debug 9333 ({type(e).__name__}).")
        print("abra o JARVIS com --remote-debugging-port=9333 e rode de novo.")
        return 2

    falhas = []
    async with websockets.connect(WS, max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "device_type": "web"}))
        s = Session(ws)
        await asyncio.sleep(1.0)

        for texto, oque in [("Jarvis, liga a luz da sala.", "resposta pronta da biblioteca"),
                            ("Jarvis, bom dia.", "saudação pronta")]:
            print(f"\n== {texto!r} ({oque}) ==")
            await frase(s, texto)
            i = await espera_destravar(cdp)
            print(f"   {i}")
            ok = not i["falando"]
            if not ok:
                falhas.append(oque)
            print("   " + ("OK: a janela destravou (falando=False)" if ok else
                           "FALHA: ficou presa em falando=True"))
            await asyncio.sleep(1.5)
        s.task.cancel()

    await cdp.close()
    print()
    if falhas:
        print(f"FALHOU em: {', '.join(falhas)}")
        return 1
    print("OK: a janela do PC não fica mais presa depois de uma resposta pronta")
    return 0


sys.exit(asyncio.run(main()))
