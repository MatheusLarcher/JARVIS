"""Confere que a janela lembra onde foi deixada: move, fecha o app, abre de novo
e verifica se voltou no mesmo lugar.

Uso: python tests/test_janela_posicao.py   (app DEV rodando com --remote-debugging-port=9333)
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CONFIG = Path(tempfile.gettempdir()) / "jarvis-desktop-dev" / "config.json"
APP_DIR = Path(__file__).resolve().parents[1] / "apps" / "desktop"
ELECTRON = APP_DIR / "node_modules" / "electron" / "dist" / "electron.exe"
NOVA_POS = {"x": 240, "y": 420}


def processos_do_app() -> list[int]:
    saida = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process electron -ErrorAction SilentlyContinue | "
         "Where-Object { $_.Path -like '*JARVIS\\apps\\desktop*' } | "
         "Select-Object -ExpandProperty Id"],
        capture_output=True, text=True).stdout
    return [int(l) for l in saida.split() if l.strip().isdigit()]


def matar_app():
    for pid in processos_do_app():
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Stop-Process -Id {pid} -Force"], capture_output=True)
    time.sleep(3)


def abrir_app():
    subprocess.Popen([str(ELECTRON), ".", "--remote-debugging-port=9333"],
                     cwd=str(APP_DIR), stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    time.sleep(14)


def posicao_salva():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8")).get("janela")
    except Exception:
        return None


def main():
    print("simulando: você arrasta a janela e depois reabre o app\n")

    matar_app()
    # "arrasta": grava a posição como se o usuário tivesse movido
    cfg = {}
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        pass
    cfg["janela"] = NOVA_POS
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(f"  posição gravada: {NOVA_POS}")

    abrir_app()
    salva = posicao_salva()
    print(f"  posição no arquivo após abrir: {salva}")

    # a janela abriu onde foi deixada?
    saida = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Add-Type -AssemblyName System.Windows.Forms; "
         "Add-Type @'\nusing System;using System.Runtime.InteropServices;\n"
         "public class W { [DllImport(\"user32.dll\")] public static extern bool "
         "GetWindowRect(IntPtr h, out RECT r); public struct RECT { public int L,T,R,B; } }\n'@; "
         "$p = Get-Process electron | Where-Object { $_.MainWindowTitle -ne '' -and "
         "$_.Path -like '*JARVIS*' } | Select-Object -First 1; "
         "if ($p) { $r = New-Object W+RECT; [void][W]::GetWindowRect($p.MainWindowHandle, [ref]$r); "
         "\"$($r.L),$($r.T)\" } else { 'sem janela' }"],
        capture_output=True, text=True).stdout.strip()
    print(f"  janela na tela em: {saida}")

    ok = salva == NOVA_POS
    print()
    if ok:
        print("OK: a janela lembra onde foi deixada")
        return 0
    print("FALHOU: a posição não foi preservada")
    return 1


sys.exit(main())
