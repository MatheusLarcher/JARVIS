"""Os agentes que fazem o trabalho de verdade.

Cada um tem seu prompt e suas ferramentas. São construídos uma vez e reusados
(montar agente do ADK custa segundos — ver agents/agent.py::aquecer).

Pra adicionar um agente: registre em config/settings.yml → agentes.lista e
declare as ferramentas dele em FERRAMENTAS, abaixo.
"""
import logging
import os

from ..config import config
from .agent import _extras_llm, _tool_abrir_programa, _tool_controlar_luz, _tool_temperatura

log = logging.getLogger("jarvis.agentes")

_construidos: dict[str, tuple] = {}     # nome -> (runner, session_service)


def nuvem_disponivel() -> tuple[str | None, dict]:
    """(modelo, extras) do provedor externo — ou (None, {}) se não dá pra usar.

    Ligado na config mas sem a chave no ambiente NÃO conta como disponível:
    isso viraria erro de autenticação no meio da resposta.
    """
    nuvem = config.settings.get("nuvem", {})
    if not nuvem.get("ativo") or not nuvem.get("modelo"):
        return None, {}
    var = nuvem.get("api_key_env")
    chave = os.environ.get(var) if var else None
    if var and not chave:
        return None, {}
    extras = {"api_key": chave} if chave else {}
    if nuvem.get("reasoning_effort"):
        # menos "pensar" = a voz começa antes (ver o comentário no settings.yml)
        extras["reasoning_effort"] = nuvem["reasoning_effort"]
    return nuvem["modelo"], extras

INSTRUCAO_BASE = (
    "Você é o JARVIS, assistente do Matheus, em português do Brasil. "
    "Sua resposta é FALADA em voz alta: uma única frase curta, sem markdown, "
    "sem listas, sem emojis e sem repetir a pergunta."
)

PROMPTS = {
    "casa": INSTRUCAO_BASE + (
        " Você cuida da casa: luzes, temperatura e dispositivos. "
        "Use as ferramentas para agir e confirme em poucas palavras o que fez."),
    "sistema": INSTRUCAO_BASE + (
        " Você cuida do computador e do próprio assistente. "
        "Se ainda não souber fazer algo, diga isso em uma frase, sem inventar."),
    "conversa": INSTRUCAO_BASE + (
        " Responda a pergunta de forma direta. "
        "Se não souber, diga que não sabe — nunca invente fatos."),
    "avancado": INSTRUCAO_BASE + (
        " Este pedido é mais difícil: pense antes de responder, mas entregue "
        "só a conclusão, em uma frase."),
}

FERRAMENTAS = {
    "casa": [_tool_controlar_luz, _tool_temperatura],
    "sistema": [_tool_abrir_programa],
    "conversa": [],
    "avancado": [],
}


def _modelo_do_agente(nome: str) -> tuple[str, dict]:
    """Agente de nuvem usa o provedor externo; os outros, o modelo local."""
    cfg_llm = config.settings["llm"]
    spec = next((a for a in config.settings.get("agentes", {}).get("lista", [])
                 if a["nome"] == nome), {})
    if spec.get("requer_nuvem"):
        modelo, extras = nuvem_disponivel()
        if modelo:
            return modelo, extras      # sem api_base: é serviço externo
        # sem chave o LiteLLM estouraria AuthenticationError, o erro seria
        # engolido e o JARVIS responderia "não entendi" pra TODA pergunta
        # difícil, sem pista nenhuma do motivo
        log.warning("agente '%s' pedia a nuvem mas não há chave; usando o "
                    "modelo local", nome)
    return cfg_llm["model"], _extras_llm(cfg_llm)


def construir(nome: str):
    """Devolve (runner, session_service) do agente, criando na primeira vez."""
    if nome in _construidos:
        return _construidos[nome]

    from google.adk.agents import Agent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    from ..mcp.loader import load_toolsets

    modelo, extras = _modelo_do_agente(nome)
    ferramentas = list(FERRAMENTAS.get(nome, []))
    if nome == "casa":
        ferramentas += load_toolsets()     # MCPs entram no agente da casa

    agente = Agent(
        name=f"jarvis_{nome}",
        model=LiteLlm(model=modelo, **extras),
        description=f"Agente {nome} do JARVIS.",
        instruction=PROMPTS.get(nome, INSTRUCAO_BASE),
        tools=ferramentas,
    )
    sessoes = InMemorySessionService()
    runner = Runner(agent=agente, app_name=f"jarvis_{nome}", session_service=sessoes)
    _construidos[nome] = (runner, sessoes)
    log.info("agente '%s' pronto (modelo %s, %d ferramentas)",
             nome, modelo, len(ferramentas))
    return _construidos[nome]


def existe(nome: str) -> bool:
    return any(a["nome"] == nome
               for a in config.settings.get("agentes", {}).get("lista", []))
