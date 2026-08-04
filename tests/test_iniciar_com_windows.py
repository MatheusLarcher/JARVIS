"""Confere a opção "Iniciar com o Windows" da engrenagem, pela interface.

O que importa aqui não é o estado na tela: é se o WINDOWS ficou com o
registro certo. Por isso cada passo clica na interface e depois lê a chave
`HKCU:\\...\\CurrentVersion\\Run` de fora do app.

Existe porque o auto-start já quebrou de dois jeitos: o app religava
`openAtLogin: true` a cada início (desmarcar não colava) e a tarefa agendada
guardava o caminho do projeto por extenso, abrindo erro de script em todo boot.

Uso: python tests/test_iniciar_com_windows.py
     (app aberto com --remote-debugging-port=9333)
"""
import asyncio
import json
import subprocess
import sys

import httpx
import websockets

CDP = "http://127.0.0.1:9333"
CHAVE = r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"


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


def registrado_no_windows() -> bool:
    """Lê o registro por fora — não confia no que o app diz de si mesmo."""
    saida = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"[bool](((Get-ItemProperty '{CHAVE}').PSObject.Properties | "
         "Where-Object {{ $_.Name -like '*jarvis*' }}))".replace("{{", "{").replace("}}", "}")],
        capture_output=True, text=True)
    return saida.stdout.strip().lower() == "true"


async def abre_engrenagem(ws):
    await _eval(ws, 'document.querySelector(".gear")?.click()')
    await asyncio.sleep(1.2)


async def estado_da_caixa(ws):
    return await _eval(ws, """(() => {
      const l = [...document.querySelectorAll('.check')]
        .find(e => e.textContent.includes('Iniciar com o Windows'))
      return l ? l.querySelector('input').checked : null
    })()""")


async def clica_a_caixa(ws):
    await _eval(ws, """(() => {
      const l = [...document.querySelectorAll('.check')]
        .find(e => e.textContent.includes('Iniciar com o Windows'))
      l && l.querySelector('input').click()
    })()""")
    await asyncio.sleep(1.5)


async def main():
    ws = await _cdp()
    falhas = []

    def confere(nome, obtido, esperado):
        ok = obtido == esperado
        print(f"  {'OK  ' if ok else 'FALHA'} {nome}: {obtido} (esperado {esperado})")
        if not ok:
            falhas.append(nome)

    await abre_engrenagem(ws)
    caixa = await estado_da_caixa(ws)
    if caixa is None:
        print("  FALHA a opção não apareceu na engrenagem")
        return 1
    print(f"\nestado inicial: caixa={caixa} registro={registrado_no_windows()}")
    confere("a caixa reflete o registro do Windows", caixa, registrado_no_windows())

    print("\n1) marcando a opção:")
    await clica_a_caixa(ws)
    confere("a caixa marcou", await estado_da_caixa(ws), True)
    confere("o Windows passou a ter o registro", registrado_no_windows(), True)

    print("\n2) desmarcando (era isto que não colava antes):")
    await clica_a_caixa(ws)
    confere("a caixa desmarcou", await estado_da_caixa(ws), False)
    confere("o registro saiu do Windows", registrado_no_windows(), False)

    print("\n3) marcando de novo, pra garantir que não é de mão única:")
    await clica_a_caixa(ws)
    confere("a caixa marcou", await estado_da_caixa(ws), True)
    confere("o registro voltou", registrado_no_windows(), True)

    # Fecha o modal antes de sair. Sem isto o app fica "pinado" (o modal aberto
    # segura a janela na tela) e o teste seguinte falha em "some depois que
    # termina" — aconteceu de verdade com o test_janela_desktop.py.
    await _eval(ws, '[...document.querySelectorAll(".btn")]'
                    '.find(b => b.textContent.trim() === "Cancelar")?.click()')
    await asyncio.sleep(0.8)
    aberto = await _eval(ws, '!!document.querySelector(".modal")')
    print(f"\nmodal fechado ao sair: {not aberto}")
    if aberto:
        falhas.append("deixou o modal aberto")

    await ws.close()
    print()
    if falhas:
        print("FALHOU em: " + ", ".join(falhas))
        return 1
    print("=== TUDO OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
