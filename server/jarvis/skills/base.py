"""Skills locais: executam intents conhecidos sem LLM.

Pra adicionar uma skill: criar módulo em skills/, herdar Skill, registrar em registry.py.
"""
from dataclasses import dataclass

from ..context.engine import DeviceContext


@dataclass
class SkillResult:
    ok: bool
    # intent de resposta da biblioteca (áudio pronto) OU texto pra TTS dinâmico
    response_intent: str | None = None
    response_text: str | None = None
    error: str | None = None


class Skill:
    intents: list[str] = []

    async def handle(self, intent_id: str, slots: dict, ctx: DeviceContext) -> SkillResult:
        raise NotImplementedError
