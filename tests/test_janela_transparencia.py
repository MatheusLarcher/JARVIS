"""Confere a transparência da janela do PC:

  - clicando fora (sem foco) e ocioso -> bem translúcida, dá pra ler o que está atrás
  - clicando nela (com foco) -> opaca
  - sem foco mas respondendo -> quase opaca (a resposta tem que ser legível)

Uso: python tests/test_janela_transparencia.py   (app com --remote-debugging-port=9333)
"""
import asyncio
import json
import subprocess
import sys

import httpx
import websockets

CDP = "http://127.0.0.1:9333"


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


async def info(ws):
    return await _eval(ws, "window.jarvisDesktop.windowInfo()", promessa=True)


async def espera_foco(ws, focada: bool, limite=8.0):
    """Espera o Windows realmente trocar o foco (não é instantâneo)."""
    t = 0.0
    while t < limite:
        i = await info(ws)
        if i["focada"] is focada:
            await asyncio.sleep(0.8)     # deixa a transição de opacidade acabar
            return await info(ws)
        await asyncio.sleep(0.3)
        t += 0.3
    return await info(ws)


def tira_o_foco():
    """Ativa outra janela, como se você fosse mexer em outra coisa."""
    subprocess.run(["powershell", "-NoProfile", "-Command", """
$p = Start-Process notepad -PassThru
Start-Sleep -Milliseconds 1500
$sh = New-Object -ComObject WScript.Shell
for ($i = 0; $i -lt 12; $i++) {
    if ($sh.AppActivate($p.Id)) { break }
    Start-Sleep -Milliseconds 400
}
Start-Sleep -Milliseconds 800
"""], capture_output=True)


def fecha_notepad():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-Process notepad -ErrorAction SilentlyContinue | Stop-Process -Force"],
                   capture_output=True)


async def main():
    ws = await _cdp()
    falhas = []

    def checa(nome, ok, extra=""):
        if not ok:
            falhas.append(nome)
        print(f"  {'OK  ' if ok else 'FALHA'} {nome} {extra}")

    await _eval(ws, "window.jarvisDesktop.state('IDLE'); window.jarvisDesktop.pin(true)")
    await asyncio.sleep(1.0)

    try:
        print("1) você vai mexer em outra janela (JARVIS parado):")
        tira_o_foco()
        i = await espera_foco(ws, focada=False)
        print(f"     {i}")
        checa("fica translúcida a ponto de ler atrás",
              i["focada"] is False and i["opacidade"] <= 0.4,
              f"(opacidade {i['opacidade']})")

        print("\n2) o JARVIS responde enquanto você está em outra janela:")
        await _eval(ws, "window.jarvisDesktop.state('THINKING')")
        await asyncio.sleep(1.5)
        i = await info(ws)
        print(f"     {i}")
        checa("volta a ficar legível pra você ler a resposta",
              i["opacidade"] >= 0.85, f"(opacidade {i['opacidade']})")

        print("\n3) terminou de responder (você continua em outra janela):")
        await _eval(ws, "window.jarvisDesktop.state('IDLE')")
        await asyncio.sleep(1.8)
        i = await info(ws)
        print(f"     {i}")
        checa("volta a sair da frente", i["opacidade"] <= 0.4,
              f"(opacidade {i['opacidade']})")

        print("\n4) você clica na janela do JARVIS:")
        await _eval(ws, "window.jarvisDesktop.focus()")
        i = await espera_foco(ws, focada=True)
        print(f"     {i}")
        checa("fica opaca ao ser focada",
              i["focada"] is True and i["opacidade"] >= 0.99,
              f"(opacidade {i['opacidade']})")
    finally:
        fecha_notepad()
        await _eval(ws, "window.jarvisDesktop.pin(false)")
        await ws.close()

    print()
    if falhas:
        print(f"FALHOU em: {', '.join(falhas)}")
        return 1
    print("OK: a janela sai da frente quando você está fazendo outra coisa")
    return 0


sys.exit(asyncio.run(main()))
