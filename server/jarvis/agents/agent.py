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
            "Suas respostas são FALADAS em voz alta e cada palavra custa tempo de síntese: "
            "responda em no máximo 2 frases curtas (idealmente até 30 palavras), direto ao ponto, "
            "sem rodeios, sem repetir a pergunta, sem markdown, sem listas e sem emojis. "
            "Não comece com saudações nem com 'Claro'. Vá direto à resposta. "
            "Use as ferramentas quando o pedido envolver a casa."
        ),
        tools=[_tool_controlar_luz, _tool_temperatura, *load_toolsets()],
    )
    _session_service = InMemorySessionService()
    _runner = Runner(agent=agent, app_name=APP, session_service=_session_service)


async def _montar_prompt(transcript: str, ctx: DeviceContext) -> str:
    history = await store.recent_history(ctx.device_id)
    hist_txt = "\n".join(f"Usuário: {h['user']}\nJARVIS: {h['jarvis']}"
                         for h in history if h["jarvis"])
    return (
        f"[contexto: dispositivo={ctx.device_id} ({ctx.device_type}), local={ctx.place}, "
        f"cômodo={ctx.room}]\n"
        + (f"[conversa recente]\n{hist_txt}\n" if hist_txt else "")
        + transcript
    )


async def ask_stream(transcript: str, ctx: DeviceContext):
    """Roda o agente e vai entregando o texto conforme ele escreve.

    Isso é o que permite começar a falar antes do LLM terminar. Cada item é um
    trecho NOVO de texto (não o acumulado).
    """
    global _runner
    if _runner is None:
        _build()
    from google.adk.agents.run_config import RunConfig, StreamingMode
    from google.genai import types

    prompt = await _montar_prompt(transcript, ctx)
    session = await _session_service.create_session(app_name=APP, user_id=ctx.user_id)
    content = types.Content(role="user", parts=[types.Part(text=prompt)])
    enviado = ""
    try:
        async for event in _runner.run_async(
                user_id=ctx.user_id, session_id=session.id, new_message=content,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE)):
            if not (event.content and event.content.parts):
                continue
            texto = "".join(p.text or "" for p in event.content.parts)
            if not texto:
                continue
            if getattr(event, "partial", False):
                # o LLM entrega token a token e um token pode ser só um pedaço
                # de palavra ("del"+"imit"+"ada") — nunca mexer no espaçamento
                novo = texto[len(enviado):] if texto.startswith(enviado) else texto
                if novo:
                    enviado += novo
                    yield novo
            elif event.is_final_response():
                # o final repete tudo: só emite o que faltou (comparação exata,
                # sem strip, pra não comer espaços e colar palavras)
                if texto.startswith(enviado):
                    resto = texto[len(enviado):]
                    if resto:
                        enviado += resto
                        yield resto
                elif not enviado:
                    enviado = texto
                    yield texto
    except Exception:
        log.exception("agente falhou")
    finally:
        # sessão é descartável (histórico vem do SQLite); sem isso vaza memória no 24/7
        try:
            await _session_service.delete_session(app_name=APP, user_id=ctx.user_id,
                                                  session_id=session.id)
        except Exception:
            pass


async def ask(transcript: str, ctx: DeviceContext) -> str | None:
    """Resposta completa (sem streaming) — usado em testes e como reserva."""
    partes = [p async for p in ask_stream(transcript, ctx)]
    texto = "".join(partes).strip()
    return texto or None
