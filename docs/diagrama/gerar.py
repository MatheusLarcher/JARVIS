"""Gera docs/diagrama.png a partir de docs/diagrama/diagrama.html.

    python docs/diagrama/gerar.py

Quem desenha de fato é o Electron (gerar.js), o mesmo que o app de bandeja já
usa. Este script só acha o binário e chama.

Por que não Chrome headless: nesta máquina o `--screenshot` sai SEM gerar nada
e SEM erro, e a porta de debug (`--remote-debugging-port`) nunca abre — nem com
perfil novo, nem com porta 0, e não há política do Chrome bloqueando. O
capturePage() do Electron não depende de porta nenhuma e funciona sempre.
"""
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
SAIDA = AQUI.parent / "diagrama.png"
ELECTRON = RAIZ / "apps" / "desktop" / "node_modules" / "electron" / "dist" / "electron.exe"


def main():
    if not ELECTRON.is_file():
        print(f"não achei o Electron em {ELECTRON}")
        print("rode `npm install` em apps/desktop")
        return 2
    antes = SAIDA.stat().st_mtime if SAIDA.is_file() else 0
    r = subprocess.run([str(ELECTRON), str(AQUI)], capture_output=True, text=True,
                       timeout=180)
    saida = (r.stdout or "").strip()
    if saida:
        print(saida)
    if not SAIDA.is_file() or SAIDA.stat().st_mtime == antes:
        print("não gerou a imagem")
        print((r.stderr or "")[-600:])
        return 1
    return 0


sys.exit(main())
