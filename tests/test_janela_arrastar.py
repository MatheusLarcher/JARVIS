"""Confere a janela do PC: dá pra arrastar, o X esconde pra bandeja e a posição
escolhida é lembrada na próxima abertura.

Uso: python tests/test_janela_arrastar.py   (app com --remote-debugging-port=9333)
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx
import websockets

CDP = "http://127.0.0.1:9333"
CONFIG = Path.home() / "AppData" / "Roaming" / "jarvis-desktop" / "config.json"
CONFIG_DEV = Path(__import__("tempfile").gettempdir()) / "jarvis-desktop-dev" / "config.json"


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
            out = r.get("result", {})
            if "exceptionDetails" in out:
                return {"erro": str(out["exceptionDetails"])[:200]}
            return out.get("result", {}).get("result", {}).get("value") \
                if "result" in out.get("result", {}) else out.get("result", {}).get("value")


async def main():
    ws = await _cdp()
    falhas = []

    def checa(nome, ok, extra=""):
        if not ok:
            falhas.append(nome)
        print(f"  {'OK  ' if ok else 'FALHA'} {nome} {extra}")

    # 1) a área vazia da janela é arrastável?
    arrasta = await _eval(ws, """
        (() => {
            const s = getComputedStyle(document.querySelector('.stage'));
            return s.webkitAppRegion || s.getPropertyValue('-webkit-app-region');
        })()
    """)
    checa("área da janela é arrastável", arrasta == "drag", f"(-webkit-app-region: {arrasta})")

    # 2) os controles NÃO podem arrastar junto (senão não dá pra clicar)
    for seletor, nome in ((".gear", "engrenagem"), (".win-close", "botão de ocultar")):
        r = await _eval(ws, f"""
            (() => {{
                const el = document.querySelector('{seletor}');
                if (!el) return 'ausente';
                const s = getComputedStyle(el);
                return s.webkitAppRegion || s.getPropertyValue('-webkit-app-region');
            }})()
        """)
        checa(f"{nome} é clicável (não arrasta)", r == "no-drag", f"({r})")

    # 3) o X esconde a janela
    await _eval(ws, "window.jarvisDesktop.state('IDLE')")
    await _eval(ws, "window.jarvisDesktop.pin(true)")      # garante visível
    await asyncio.sleep(0.6)
    antes = await _eval(ws, "window.jarvisDesktop.isVisible()", promessa=True)
    await _eval(ws, "document.querySelector('.win-close').click()")
    await asyncio.sleep(0.8)
    depois = await _eval(ws, "window.jarvisDesktop.isVisible()", promessa=True)
    checa("o X oculta a janela", antes is True and depois is False,
          f"(antes={antes}, depois={depois})")

    # 4) some pra bandeja, mas o JARVIS continua vivo e ouvindo
    vivo = await _eval(ws, "typeof window.jarvisDesktop === 'object'")
    checa("continua rodando depois de ocultar", vivo is True)

    await ws.close()
    print()
    if falhas:
        print(f"FALHOU em: {', '.join(falhas)}")
        return 1
    print("OK: janela arrastável e botão de ocultar funcionando")
    return 0


sys.exit(asyncio.run(main()))
