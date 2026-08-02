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


def phonetic(word: str) -> str:
    """Reduz o que o STT costuma trocar em português.

    "jarvis" sai como "jarves", "javis", "jarvez" e até "já fiz" — todos viram
    a mesma forma aqui, porque v/f e z/s soam parecido e o h é mudo.
    """
    w = word
    for a, b in (("lh", "l"), ("nh", "n"), ("ch", "x"), ("qu", "c"), ("ss", "s"),
                 ("rr", "r"), ("ph", "f")):
        w = w.replace(a, b)
    table = str.maketrans({"v": "f", "z": "s", "ç": "s", "k": "c", "w": "f",
                           "y": "i", "h": "", "j": "j", "g": "j"})
    return w.translate(table)


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
        self.key_ph = phonetic(self.keyword)
        self.max_edits = int(cfg.get("fuzzy_max_edits", 2))
        # palavras que costumam vir grudadas antes do nome
        self.prefixes = {"hey", "ei", "ok", "ola", "oi", "e", "o"}

    def _distancia(self, word: str) -> int:
        return min(_edits(word, self.keyword), _edits(phonetic(word), self.key_ph))

    def _is_keyword(self, word: str) -> bool:
        if len(word) < 4:            # curto demais casaria com qualquer coisa
            return False
        # palavra curta tem menos evidência: exige estar mais perto
        allowed = self.max_edits if len(word) >= 5 else 1
        return self._distancia(word) <= allowed

    def _parece_keyword(self, word: str) -> bool:
        """Parecido, mas não o bastante pra disparar sozinho.

        O STT escreve coisas como "Jairus", "Já Luiz", "Já vi". Aceitar isso
        direto encheria de falso positivo (a TV ligada acorda o JARVIS), então
        só vale quando vem seguido de um comando que a gente conhece.
        """
        if len(word) < 4:
            return False
        return self._distancia(word) <= self.max_edits + 1

    def match(self, transcript: str) -> tuple[bool, str]:
        """(chamou?, comando restante da mesma frase)."""
        words = normalize(transcript).split()
        if not words:
            return False, ""

        def strip_prefix(rest_before: list[str], i: int) -> list[str]:
            # tira "hey/ok/ei" que só existiam por causa do nome
            if i > 0 and words[i - 1] in self.prefixes:
                return rest_before[:-1]
            return rest_before

        for i, w in enumerate(words):
            if self._is_keyword(w):
                rest = strip_prefix(words[:i], i) + words[i + 1:]
                return True, " ".join(rest).strip()

        # o STT às vezes parte o nome em duas ("jarvis" -> "já fiz", "jar vis")
        for i in range(len(words) - 1):
            if self._is_keyword(words[i] + words[i + 1]):
                rest = strip_prefix(words[:i], i) + words[i + 2:]
                return True, " ".join(rest).strip()

        # último recurso: nome mal transcrito ("Jairus", "Já Luiz") só conta se
        # o que vem depois for um comando que a gente reconhece
        for i, w in enumerate(words):
            if self._parece_keyword(w):
                rest = " ".join(strip_prefix(words[:i], i) + words[i + 1:]).strip()
                if rest and self._eh_comando(rest):
                    return True, rest
        for i in range(len(words) - 1):
            if self._parece_keyword(words[i] + words[i + 1]):
                rest = " ".join(strip_prefix(words[:i], i) + words[i + 2:]).strip()
                if rest and self._eh_comando(rest):
                    return True, rest
        return False, ""

    def _eh_comando(self, texto: str) -> bool:
        """O resto da frase é um comando conhecido? (evita falso positivo)"""
        from ..intents.router import intent_router
        return intent_router.match(texto) is not None


matcher = WakeMatcher()
