import re

from ..context.engine import DeviceContext
from ..system.apps import abrir
from .base import Skill, SkillResult

# "abre o bloco de notas" -> slot programa = "o bloco de notas"; tira o artigo
# aqui (em vez de no regex) pra não precisar prever toda variação de artigo/plural
_ARTIGO = re.compile(r"^(?:o|a|os|as|um|uma)\s+", re.IGNORECASE)


class AppsSkill(Skill):
    """Abre programas do Windows. Resolvido por regex (0ms) — não passa pelo
    LLM: testado que o modelo local (qwen3.5:0.8b) não chama função de forma
    confiável (0/8 tentativas), então depender dele pra ação real não serve.
    Ver server/jarvis/agents/agent.py::_tool_abrir_programa e docs/MEMORIA.md.
    """
    intents = ["system.abrir_programa"]

    async def handle(self, intent_id: str, slots: dict, ctx: DeviceContext) -> SkillResult:
        nome = _ARTIGO.sub("", (slots.get("programa") or "").strip())
        if not nome:
            return SkillResult(ok=False, response_text="Abrir o quê?")
        resultado = await abrir(nome)
        if resultado["ok"]:
            return SkillResult(ok=True, response_text=f"Abrindo {resultado['aberto']}.")
        return SkillResult(ok=False, response_text=f"Não achei o programa {nome}.")
