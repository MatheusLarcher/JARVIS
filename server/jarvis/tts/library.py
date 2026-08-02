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

    @staticmethod
    def url_de(path: Path, prefixo: str) -> str:
        """URL com a versão do arquivo no fim.

        Sem isso, trocar a voz não muda a URL (o nome do arquivo é o mesmo) e os
        aparelhos continuam tocando o áudio antigo que ficou no cache deles.
        """
        try:
            versao = int(path.stat().st_mtime)
        except OSError:
            versao = 0
        return f"{prefixo}/{path.name}?v={versao}"

    def texto_qualquer(self, intent: str) -> str | None:
        """Uma das frases configuradas, mesmo sem áudio pronto.

        Rede de segurança: intent novo em responses.yml só ganha wav depois de
        rodar scripts/build_library.py. Sem isto, o JARVIS ficaria MUDO nesse
        intervalo — o texto vai pro TTS normal e ele fala do mesmo jeito.
        """
        frases = self.responses.get(intent) or []
        return random.choice(frases) if frases else None

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
