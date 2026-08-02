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


class _FiltroPensamento:
    """Tira o raciocínio (<think>...</think>) do texto que vai virar fala.

    Os Qwen3.x às vezes "pensam em voz alta" mesmo com /no_think, e isso não
    pode ser falado. Funciona no stream, sem esperar a resposta fechar.
    """

    ABRE, FECHA = "<think>", "</think>"

    def __init__(self):
        self.pensando = False
        self.pendente = ""      # pedaço de tag que pode ter vindo partido

    @staticmethod
    def _inicio_de_tag(buffer: str, tag: str) -> int:
        """Quantos caracteres do fim do buffer podem ser o começo da tag."""
        for n in range(min(len(tag) - 1, len(buffer)), 0, -1):
            if tag.startswith(buffer[-n:]):
                return n
        return 0

    def feed(self, texto: str) -> str:
        buffer = self.pendente + texto
        self.pendente = ""
        saida = []
        while buffer:
            alvo = self.FECHA if self.pensando else self.ABRE
            pos = buffer.find(alvo)
            if pos == -1:
                # a tag pode estar chegando partida: segura só esse pedacinho
                n = self._inicio_de_tag(buffer, alvo)
                if n:
                    self.pendente = buffer[-n:]
                    buffer = buffer[:-n]
                if not self.pensando:
                    saida.append(buffer)
                return "".join(saida)
            if not self.pensando:
                saida.append(buffer[:pos])
            buffer = buffer[pos + len(alvo):]
            self.pensando = not self.pensando
        return "".join(saida)


def _instrucao(llm_cfg: dict) -> str:
    texto = (
        "Você é o JARVIS, assistente pessoal residencial do Matheus, em português do Brasil. "
        "Suas respostas são FALADAS em voz alta e cada palavra custa tempo de síntese: "
        "responda em no máximo 2 frases curtas (idealmente até 30 palavras), direto ao ponto, "
        "sem rodeios, sem repetir a pergunta, sem markdown, sem listas e sem emojis. "
        "Não comece com saudações nem com 'Claro'. Vá direto à resposta. "
        "Use as ferramentas quando o pedido envolver a casa."
    )
    # nos modelos Qwen3.x isto desliga o "pensar antes de responder"
    if llm_cfg.get("no_think"):
        texto += " /no_think"
    return texto


def _build():
    global _runner, _session_service
    from google.adk.agents import Agent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    llm_cfg = config.settings["llm"]
    # api_base é o que aponta pro Ollama local; sem ele o LiteLLM tenta a nuvem
    extras = {"api_base": llm_cfg["api_base"]} if llm_cfg.get("api_base") else {}
    agent = Agent(
        name="jarvis",
        model=LiteLlm(model=llm_cfg["model"], **extras),
        description="JARVIS, assistente pessoal do Matheus.",
        instruction=_instrucao(llm_cfg),
        tools=[_tool_controlar_luz, _tool_temperatura, *load_toolsets()],
    )
    _session_service = InMemorySessionService()
    _runner = Runner(agent=agent, app_name=APP, session_service=_session_service)


async def aquecer():
    """Monta o agente e abre a conexão com o provedor no start do servidor.

    Sem isto, a PRIMEIRA pergunta paga tudo isso e demora ~5,5s em vez de ~0,8s
    (medido em tests/diag_llm_stream.py).
    """
    try:
        if _runner is None:
            _build()
        from litellm import acompletion
        cfg = config.settings["llm"]
        extras = {"api_base": cfg["api_base"]} if cfg.get("api_base") else {}
        # com modelo local, esta chamada também tira o modelo do disco e o
        # deixa carregado — a primeira pergunta de verdade já sai rápida
        await acompletion(model=cfg["model"],
                          messages=[{"role": "user", "content": "oi"}],
                          max_tokens=1, **extras)
        log.info("agente pronto (aquecido): %s", cfg["model"])
    except Exception as e:
        log.warning("não deu pra aquecer o agente agora: %s", e)


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
    filtro = _FiltroPensamento()
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
                    limpo = filtro.feed(novo)
                    if limpo:
                        yield limpo
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
