"""Descobre quanto do tempo de resposta é do LLM e quanto é do ADK em volta.

Compara, na mesma pergunta:
  1. LiteLLM direto (o mínimo possível)
  2. ADK sem ferramentas
  3. ADK com as ferramentas do JARVIS (o que roda hoje)

Uso: python tests/diag_adk_overhead.py     (env jarvis)
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.config import config  # noqa: E402

PERGUNTA = "quem foi santos dumont"
INSTRUCAO = ("Você é o JARVIS. Responda em uma frase curta, em português, "
             "sem markdown.")


async def litellm_direto():
    from litellm import acompletion
    t0 = time.perf_counter()
    resp = await acompletion(
        model=config.settings["llm"]["model"],
        messages=[{"role": "system", "content": INSTRUCAO},
                  {"role": "user", "content": PERGUNTA}],
        stream=True, max_tokens=120)
    async for pedaco in resp:
        if pedaco.choices[0].delta.content:
            return time.perf_counter() - t0
    return time.perf_counter() - t0


async def via_adk(com_ferramentas: bool):
    from google.adk.agents import Agent
    from google.adk.agents.run_config import RunConfig, StreamingMode
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from jarvis.agents.agent import _tool_controlar_luz, _tool_temperatura

    agente = Agent(
        name="teste", model=LiteLlm(model=config.settings["llm"]["model"]),
        description="teste", instruction=INSTRUCAO,
        tools=[_tool_controlar_luz, _tool_temperatura] if com_ferramentas else [])
    sessoes = InMemorySessionService()
    runner = Runner(agent=agente, app_name="teste", session_service=sessoes)

    t0 = time.perf_counter()
    sessao = await sessoes.create_session(app_name="teste", user_id="m")
    t_sessao = time.perf_counter() - t0
    conteudo = types.Content(role="user", parts=[types.Part(text=PERGUNTA)])
    async for evento in runner.run_async(
            user_id="m", session_id=sessao.id, new_message=conteudo,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE)):
        if evento.content and evento.content.parts:
            texto = "".join(p.text or "" for p in evento.content.parts)
            if texto.strip():
                return time.perf_counter() - t0, t_sessao
    return time.perf_counter() - t0, t_sessao


async def main():
    print(f"pergunta: {PERGUNTA!r}\n")

    t = await litellm_direto()
    print(f"  LiteLLM direto            : {t:.2f}s até a 1ª palavra")

    t, t_sessao = await via_adk(False)
    print(f"  ADK sem ferramentas       : {t:.2f}s  (criar sessão: {t_sessao:.2f}s)")

    t, t_sessao = await via_adk(True)
    print(f"  ADK com as ferramentas    : {t:.2f}s  (criar sessão: {t_sessao:.2f}s)")


asyncio.run(main())
