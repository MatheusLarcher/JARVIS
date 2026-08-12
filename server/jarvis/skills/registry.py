from .apps import AppsSkill
from .base import Skill
from .info import InfoSkill
from .lights import LightsSkill
from .social import SocialSkill

_skills: list[Skill] = [LightsSkill(), InfoSkill(), SocialSkill(), AppsSkill()]

_by_intent: dict[str, Skill] = {}
for s in _skills:
    for intent_id in s.intents:
        _by_intent[intent_id] = s


def skill_for(intent_id: str) -> Skill | None:
    return _by_intent.get(intent_id)
