"""Gera tokens novos pros aparelhos e atualiza quem já guardou o antigo.

Use quando um token vazar (por exemplo: ele esteve no histórico do git e o
repositório vai virar público). Token vazado não se conserta apagando o
arquivo — o valor antigo continua lá. Só trocando.

    python server/scripts/trocar_tokens.py            # mostra o que faria
    python server/scripts/trocar_tokens.py --aplicar  # troca de verdade

Depois de aplicar: reinicie o servidor e o app da bandeja.
"""
import json
import re
import secrets
import shutil
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DEVICES = RAIZ / "config" / "devices.yml"
# o app de bandeja guarda uma cópia do token; sem atualizar aqui ele fica
# tentando entrar com o antigo e o servidor recusa (4401)
CFG_DESKTOP = Path.home() / "AppData" / "Roaming" / "jarvis-desktop" / "config.json"

LINHA_TOKEN = re.compile(r"^(\s*token:\s*)(\S+)\s*$", re.M)
LINHA_DEVICE = re.compile(r"^  ([\w-]+):\s*$", re.M)


def novo() -> str:
    return "tk_" + secrets.token_urlsafe(24)


def main():
    aplicar = "--aplicar" in sys.argv
    if not DEVICES.is_file():
        print(f"não achei {DEVICES}")
        return 2

    texto = DEVICES.read_text(encoding="utf-8")
    # mapeia device -> token novo, na ordem em que aparecem
    devices = LINHA_DEVICE.findall(texto)
    novos = {}
    i = 0

    def troca(m):
        nonlocal i
        dev = devices[i] if i < len(devices) else f"?{i}"
        i += 1
        n = novo()
        novos[dev] = n
        return f"{m.group(1)}{n}"

    saida = LINHA_TOKEN.sub(troca, texto)
    if not novos:
        print("nenhum token encontrado no arquivo")
        return 1

    for dev, tok in novos.items():
        print(f"  {dev:18s} -> {tok}")

    if not aplicar:
        print("\n(simulação — rode com --aplicar pra valer)")
        return 0

    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = DEVICES.with_suffix(f".yml.bak-{carimbo}")
    shutil.copy2(DEVICES, backup)
    DEVICES.write_text(saida, encoding="utf-8")
    print(f"\ndevices.yml atualizado (backup em {backup.name})")

    if CFG_DESKTOP.is_file():
        try:
            cfg = json.loads(CFG_DESKTOP.read_text(encoding="utf-8"))
            dev = cfg.get("device")
            if dev in novos:
                shutil.copy2(CFG_DESKTOP, CFG_DESKTOP.with_suffix(f".json.bak-{carimbo}"))
                cfg["token"] = novos[dev]
                CFG_DESKTOP.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
                print(f"app da bandeja atualizado ({dev})")
            else:
                print(f"app da bandeja usa o device {dev!r}, que não está no devices.yml")
        except Exception as e:
            print(f"não consegui atualizar o app da bandeja: {e}")

    print("\nAgora reinicie o servidor e o app da bandeja.")
    print("Nos celulares/relógio, informe o token novo na tela de configuração.")
    return 0


sys.exit(main())
