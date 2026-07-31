from ..context.engine import DeviceContext, context_engine
from ..home_assistant.client import ha, resolve_light_entity
from .base import Skill, SkillResult


class LightsSkill(Skill):
    intents = ["light.turn_on", "light.turn_off"]

    async def handle(self, intent_id: str, slots: dict, ctx: DeviceContext) -> SkillResult:
        room = context_engine.resolve_room(ctx, slots.get("room"))
        if not room:
            return SkillResult(ok=False, response_intent="ambiguous_room")
        entity = resolve_light_entity(room)
        if not entity:
            return SkillResult(ok=False, response_intent="error",
                               error=f"sem luz mapeada pro cômodo {room}")
        service = "turn_on" if intent_id == "light.turn_on" else "turn_off"
        ok = await ha.call_service("light", service, entity)
        if not ok:
            return SkillResult(ok=False, response_intent="error", error="falha no Home Assistant")
        return SkillResult(ok=True,
                           response_intent="light_on_success" if service == "turn_on" else "light_off_success")
