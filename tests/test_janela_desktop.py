"""Confere o comportamento da janela do PC:

  - aparece ao ser chamada;
  - NÃO some enquanto está ouvindo/pensando/executando;
  - NÃO some enquanto ainda está falando a resposta;
  - some sozinha alguns segundos depois de tudo terminar.

Uso: python tests/test_janela_desktop.py     (app com --remote-debugging-port=9333)
"""
import asyncio
import json
import sys

import httpx
import websockets

CDP = "http://127.0.0.1:9333"


async def _cdp():
    async with httpx.AsyncClient() as c:
        alvos = (await c.get(f"{CDP}/json")).json()
    pagina = next(p for p in alvos if p.get("type") == "page")
    return await websockets.connect(pagina["webSocketDebuggerUrl"], max_size=None)


async def _eval(ws, expr, i=[0], await_promise=False):
    i[0] += 1
    await ws.send(json.dumps({"id": i[0], "method": "Runtime.evaluate",
                              "params": {"expression": expr, "returnByValue": True,
                                         "awaitPromise": await_promise}}))
    while True:
        r = json.loads(await ws.recv())
        if r.get("id") == i[0]:
            return r.get("result", {}).get("result", {}).get("value")


async def visivel(ws) -> bool:
    # pergunta ao Electron, não ao Chromium: com backgroundThrottling desligado
    # o document.visibilityState continua "visible" com a janela escondida
    return await _eval(ws, "window.jarvisDesktop.isVisible()", await_promise=True) is True


async def main():
    ws = await _cdp()
    falhas = []
    # o app está ouvindo a sala de verdade; um barulho acordaria o JARVIS no
    # meio do teste e bagunçaria a medição — corta a conexão durante o teste
    await _eval(ws, "window.__wsBackup = WebSocket; window.WebSocket = function(){ "
                    "throw new Error('desligado para o teste') }")
    await _eval(ws, "(window.__pausa = true)")

    async def checa(nome, esperado_visivel):
        v = await visivel(ws)
        ok = v == esperado_visivel
        if not ok:
            falhas.append(nome)
        print(f"  {'OK  ' if ok else 'FALHA'} {nome}: janela "
              f"{'visível' if v else 'escondida'} "
              f"(esperado {'visível' if esperado_visivel else 'escondida'})")

    print("simulando uma interação completa pelo app do PC:\n")

    await _eval(ws, "window.jarvisDesktop.state('IDLE')")
    await asyncio.sleep(4.5)                       # deixa esconder

    await _eval(ws, "window.jarvisDesktop.wake()")
    await asyncio.sleep(0.6)
    await checa("ao ser chamado, aparece", True)

    for estado in ("LISTENING", "THINKING", "EXECUTING"):
        await _eval(ws, f"window.jarvisDesktop.state('{estado}')")
        await asyncio.sleep(4.0)                   # mais que o tempo de esconder
        await checa(f"continua na tela em {estado}", True)

    # terminou de processar, mas ainda está falando a resposta
    await _eval(ws, "window.jarvisDesktop.speaking(true)")
    await _eval(ws, "window.jarvisDesktop.state('IDLE')")
    await asyncio.sleep(4.5)
    await checa("continua na tela enquanto fala", True)

    # acabou de falar: agora pode sumir
    await _eval(ws, "window.jarvisDesktop.speaking(false)")
    await asyncio.sleep(4.5)
    await checa("some depois que termina", False)

    await _eval(ws, "window.WebSocket = window.__wsBackup")   # devolve como estava
    await ws.close()
    print()
    if falhas:
        print(f"FALHOU em: {', '.join(falhas)}")
        return 1
    print("OK: a janela só some quando o JARVIS termina de verdade")
    return 0


sys.exit(asyncio.run(main()))
