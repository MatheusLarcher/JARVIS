from datetime import datetime

from ..context.engine import DeviceContext
from ..home_assistant.client import ha
from .base import Skill, SkillResult


class InfoSkill(Skill):
    intents = ["info.time", "info.temperature"]

    async def handle(self, intent_id: str, slots: dict, ctx: DeviceContext) -> SkillResult:
        if intent_id == "info.time":
            now = datetime.now()
            text = f"São {now.hour} horas e {now.minute:02d} minutos."
            if now.minute == 0:
                text = f"São {now.hour} horas em ponto."
            return SkillResult(ok=True, response_text=text)
        temp = await ha.temperature()
        if temp is None:
            return SkillResult(ok=False, response_intent="error", error="sensor indisponível")
        return SkillResult(ok=True, response_text=f"A temperatura ambiente é de {temp:.0f} graus.")
