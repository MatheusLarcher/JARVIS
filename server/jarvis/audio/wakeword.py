"""Reconhecimento da palavra-chave dentro da transcrição.

O STT nem sempre escreve "jarvis" igual (sai "jarves", "javis", "jarvez"...),
então a comparação é por distância de edição, não igualdade.

Também separa o comando dito na MESMA frase:
    "jarvis liga a luz da sala"  → (True, "liga a luz da sala")
    "liga a luz, jarvis"         → (True, "liga a luz")
    "jarvis"                     → (True, "")           só chamou
    "hoje o dia foi bom"         → (False, "")
"""
import re
import unicodedata

from ..config import config


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w\s]", " ", text)


def _edits(a: str, b: str) -> int:
    """Distância de Levenshtein (palavras curtas, custo irrelevante)."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


class WakeMatcher:
    def __init__(self):
        cfg = config.settings["wake_word"]
        self.keyword = normalize(cfg.get("keyword", "jarvis")).strip()
        self.max_edits = int(cfg.get("fuzzy_max_edits", 2))
        # palavras que costumam vir grudadas antes do nome
        self.prefixes = {"hey", "ei", "ok", "ola", "oi", "e", "o"}

    def _is_keyword(self, word: str) -> bool:
        if len(word) < 4:            # curto demais casaria com qualquer coisa
            return False
        allowed = self.max_edits if len(word) >= 5 else 1
        return _edits(word, self.keyword) <= allowed

    def match(self, transcript: str) -> tuple[bool, str]:
        """(chamou?, comando restante da mesma frase)."""
        words = normalize(transcript).split()
        if not words:
            return False, ""
        for i, w in enumerate(words):
            if self._is_keyword(w):
                rest = words[:i] + words[i + 1:]
                # tira "hey/ok/ei" que só existiam por causa do nome
                if i > 0 and words[i - 1] in self.prefixes:
                    rest = words[:i - 1] + words[i + 1:]
                return True, " ".join(rest).strip()
        return False, ""


matcher = WakeMatcher()
