"""Agente Google ADK — fallback quando o Intent Router não conhece o pedido.

LLM via LiteLlm (provedor trocável em config/settings.yml → llm.model).
Ferramentas: controle da casa e informações; MCPs entram aqui no futuro
(jarvis/mcp/ → MCPToolset do ADK).
"""
import logging

from ..config import config
from ..context.engine import DeviceContext
from ..home_assistant.client import ha, resolve_light_entity
from ..mcp.loader import load_toolsets
from ..memory.db import store

log = logging.getLogger("jarvis.agent")

_runner = None
_session_service = None
APP = "jarvis"


async def _tool_controlar_luz(acao: str, comodo: str) -> dict:
    """Liga ou desliga a luz de um cômodo. acao: 'ligar' ou 'desligar'. comodo: sala, quarto, escritorio."""
    entity = resolve_light_entity(comodo)
    if not entity:
        return {"ok": False, "erro": f"cômodo desconhecido: {comodo}"}
    ok = await ha.call_service("light", "turn_on" if acao == "ligar" else "turn_off", entity)
    return {"ok": ok}


async def _tool_temperatura() -> dict:
    """Retorna a temperatura ambiente atual em graus Celsius."""
    return {"temperatura_c": await ha.temperature()}


def _build():
    global _runner, _session_service
    from google.adk.agents import Agent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    llm_cfg = config.settings["llm"]
    agent = Agent(
        name="jarvis",
        model=LiteLlm(model=llm_cfg["model"]),
        description="JARVIS, assistente pessoal do Matheus.",
        instruction=(
            "Você é o JARVIS, assistente pessoal residencial do Matheus, em português do Brasil. "
            "Suas respostas serão faladas em voz alta: seja curto (1 a 2 frases), direto e natural, "
            "sem markdown, sem listas, sem emojis. Use as ferramentas quando o pedido envolver a casa."
        ),
        tools=[_tool_controlar_luz, _tool_temperatura, *load_toolsets()],
    )
    _session_service = InMemorySessionService()
    _runner = Runner(agent=agent, app_name=APP, session_service=_session_service)


async def ask(transcript: str, ctx: DeviceContext) -> str | None:
    """Roda o agente e devolve o texto final da resposta."""
    global _runner
    if _runner is None:
        _build()
    from google.genai import types

    history = await store.recent_history(ctx.device_id)
    hist_txt = "\n".join(f"Usuário: {h['user']}\nJARVIS: {h['jarvis']}" for h in history if h["jarvis"])
    prompt = (
        f"[contexto: dispositivo={ctx.device_id} ({ctx.device_type}), local={ctx.place}, "
        f"cômodo={ctx.room}]\n"
        + (f"[conversa recente]\n{hist_txt}\n" if hist_txt else "")
        + transcript
    )
    session = await _session_service.create_session(app_name=APP, user_id=ctx.user_id)
    content = types.Content(role="user", parts=[types.Part(text=prompt)])
    final = None
    try:
        async for event in _runner.run_async(user_id=ctx.user_id, session_id=session.id,
                                             new_message=content):
            if event.is_final_response() and event.content and event.content.parts:
                final = "".join(p.text or "" for p in event.content.parts).strip()
    except Exception:
        log.exception("agente falhou")
        return None
    finally:
        # sessão é descartável (histórico vem do SQLite); sem isso vaza memória no 24/7
        try:
            await _session_service.delete_session(app_name=APP, user_id=ctx.user_id,
                                                  session_id=session.id)
        except Exception:
            pass
    return final or None
