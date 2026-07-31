"""Intent Router local: regex normalizada (sem acento) sobre a transcrição.

Camadas futuras: embeddings de similaridade antes do fallback pro agente.
"""
import re
import unicodedata
from dataclasses import dataclass, field

from ..config import config


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w\s]", " ", text).strip()


@dataclass
class IntentMatch:
    intent_id: str
    slots: dict = field(default_factory=dict)
    response_intent: str | None = None


class IntentRouter:
    def __init__(self):
        self._compiled: list[tuple[dict, list[re.Pattern]]] = []
        for intent in config.intents:
            patterns = [re.compile(p, re.IGNORECASE) for p in intent.get("patterns", [])]
            self._compiled.append((intent, patterns))

    def match(self, transcript: str) -> IntentMatch | None:
        text = normalize(transcript)
        # remove o prefixo "jarvis" se o STT capturou junto
        text = re.sub(r"^\s*jarvis[\s,]*", "", text)
        for intent, patterns in self._compiled:
            for pat in patterns:
                m = pat.search(text)
                if m:
                    slots = {k: v for k, v in m.groupdict().items() if v}
                    return IntentMatch(intent["id"], slots, intent.get("response_intent"))
        return None


intent_router = IntentRouter()
