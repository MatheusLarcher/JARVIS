import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "server" / "data"


def _load_env():
    """Carrega config/.env (KEY=valor) pro os.environ sem sobrescrever o que já existe."""
    env_file = CONFIG_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def _load(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Config:
    def __init__(self):
        _load_env()
        self.settings = _load("settings.yml")
        self.devices = _load("devices.yml")["devices"]
        self.house = _load("house.yml")
        self.responses = _load("responses.yml")["responses"]
        # apelido de programa -> alvo do os.startfile (ver system/apps.py)
        self.apps = _load("apps.yml").get("apps", {})
        self.intents = []
        for p in sorted((CONFIG_DIR / "intents").glob("*.yml")):
            with open(p, encoding="utf-8") as f:
                self.intents += (yaml.safe_load(f) or {}).get("intents", [])

    def env_secret(self, key_env: str) -> str | None:
        return os.environ.get(key_env)


config = Config()
