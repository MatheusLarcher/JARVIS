"""Cumprimentos: resposta pronta, sem LLM.

Isso existe por medida de segurança e de velocidade. O modelo pequeno, solto,
respondia "bom dia" com texto inventado — e às vezes com o próprio molde do
prompt ("<uma frase curta>") indo pro alto-falante. Aqui sai áudio já gerado,
em ~0ms, e a saudação ainda acompanha a hora do dia.
"""
from datetime import datetime

from ..context.engine import DeviceContext
from .base import Skill, SkillResult


def saudacao_da_hora(agora: datetime | None = None) -> str:
    h = (agora or datetime.now()).hour
    if 5 <= h < 12:
        return "saudacao_manha"
    if 12 <= h < 18:
        return "saudacao_tarde"
    if 18 <= h < 24:
        return "saudacao_noite"
    return "saudacao"          # madrugada: nada de "boa noite" às 3 da manhã


class SocialSkill(Skill):
    intents = ["social.greeting", "social.thanks", "social.bye"]

    async def handle(self, intent_id: str, slots: dict, ctx: DeviceContext) -> SkillResult:
        if intent_id == "social.greeting":
            return SkillResult(ok=True, response_intent=saudacao_da_hora())
        if intent_id == "social.thanks":
            return SkillResult(ok=True, response_intent="agradecimento")
        return SkillResult(ok=True, response_intent="despedida")
