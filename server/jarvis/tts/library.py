"""Biblioteca de respostas prontas: intent → wavs pré-gerados, com variação aleatória.

Os arquivos são gerados por scripts/build_library.py e ficam em server/data/library/<intent>/.
"""
import random
from pathlib import Path

from ..config import ROOT, config


class ResponseLibrary:
    def __init__(self):
        self.dir = ROOT / config.settings["tts"]["library_dir"]
        self.responses = config.responses

    def pick(self, intent: str) -> tuple[str, Path] | None:
        """Sorteia uma variação pronta. Retorna (texto, caminho) ou None."""
        folder = self.dir / intent
        if not folder.is_dir():
            return None
        files = sorted(folder.glob("*.mp3")) + sorted(folder.glob("*.wav"))
        if not files:
            return None
        texts = self.responses.get(intent, [])
        f = random.choice(files)
        # convenção: NN_<slug>.mp3 casa com a posição na lista de frases
        try:
            idx = int(f.name.split("_")[0])
            text = texts[idx] if idx < len(texts) else ""
        except (ValueError, IndexError):
            text = ""
        return text, f


library = ResponseLibrary()
