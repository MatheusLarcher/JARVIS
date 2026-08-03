"""Endereço e token pros testes, lidos do config — nunca escritos no código.

Antes cada teste trazia o token do `web-dev` na mão. Isso vaza credencial pro
histórico do git (e o repo vai ser público), e ainda quebra todos os testes de
uma vez quando o token é trocado.

Uso:
    from conexao import ws_url
    async with websockets.connect(ws_url()) as ws:
"""
from pathlib import Path
from urllib.parse import quote

import yaml

RAIZ = Path(__file__).resolve().parents[1]
DEVICES = RAIZ / "config" / "devices.yml"
HOST_PADRAO = "127.0.0.1:8040"


def token_de(device_id: str = "web-dev") -> str:
    if not DEVICES.is_file():
        raise SystemExit(
            f"não achei {DEVICES}.\n"
            "copie config/devices.example.yml para config/devices.yml e "
            "gere os seus tokens.")
    devices = (yaml.safe_load(DEVICES.read_text(encoding="utf-8")) or {}).get("devices", {})
    dev = devices.get(device_id)
    if not dev or not dev.get("token"):
        raise SystemExit(f"o device {device_id!r} não tem token em {DEVICES}")
    return dev["token"]


def ws_url(device_id: str = "web-dev", host: str = HOST_PADRAO) -> str:
    return f"ws://{host}/ws/{device_id}?token={quote(token_de(device_id))}"
