"""Quanto as ferramentas e o histórico custam num modelo pequeno.

No bench direto o qwen3.5:0.8b responde em 0,26s, mas pelo caminho do JARVIS
levou 2,4s. Aqui separamos o que pesa: declaração de ferramentas, histórico e
instrução.

Uso: python tests/diag_llm_tools.py     (env jarvis)
"""
import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.config import config  # noqa: E402

PERGUNTA = "quem foi santos dumont"
REPETICOES = 3
INSTRUCAO_CURTA = "Você é o JARVIS. Responda em uma frase curta, em português."
INSTRUCAO_LONGA = (
    "Você é o JARVIS, assistente pessoal residencial do Matheus, em português do Brasil. "
    "Suas respostas são FALADAS em voz alta e cada palavra custa tempo de síntese: "
    "responda em no máximo 2 frases curtas (idealmente até 30 palavras), direto ao ponto, "
    "sem rodeios, sem repetir a pergunta, sem markdown, sem listas e sem emojis. "
    "Não comece com saudações nem com 'Claro'. Vá direto à resposta. "
    "Use as ferramentas quando o pedido envolver a casa."
)


async def mede_adk(com_ferramentas: bool, instrucao: str) -> float:
    from google.adk.agents import Agent
    from google.adk.agents.run_config import RunConfig, StreamingMode
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from jarvis.agents.agent import (_extras_llm, _tool_controlar_luz,
                                     _tool_temperatura)

    cfg = config.settings["llm"]
    agente = Agent(name="t", model=LiteLlm(model=cfg["model"], **_extras_llm(cfg)),
                   description="teste", instruction=instrucao,
                   tools=[_tool_controlar_luz, _tool_temperatura] if com_ferramentas else [])
    sessoes = InMemorySessionService()
    runner = Runner(agent=agente, app_name="t", session_service=sessoes)

    tempos = []
    for _ in range(REPETICOES + 1):      # a 1ª é descartada (aquecimento)
        sessao = await sessoes.create_session(app_name="t", user_id="m")
        conteudo = types.Content(role="user", parts=[types.Part(text=PERGUNTA)])
        t0 = time.perf_counter()
        primeiro = None
        async for ev in runner.run_async(user_id="m", session_id=sessao.id,
                                         new_message=conteudo,
                                         run_config=RunConfig(
                                             streaming_mode=StreamingMode.SSE)):
            if ev.content and ev.content.parts:
                txt = "".join(p.text or "" for p in ev.content.parts)
                if txt.strip() and primeiro is None:
                    primeiro = time.perf_counter() - t0
                    break
        tempos.append(primeiro if primeiro else time.perf_counter() - t0)
    return statistics.median(tempos[1:])


async def main():
    print(f"modelo: {config.settings['llm']['model']}")
    print(f"pergunta: {PERGUNTA!r} | {REPETICOES}x cada (1ª descartada)\n")
    print(f"  {'configuração':38s} {'1ª palavra':>11s}")
    combos = [
        ("instrução curta, sem ferramentas", False, INSTRUCAO_CURTA),
        ("instrução curta, COM ferramentas", True, INSTRUCAO_CURTA),
        ("instrução longa, sem ferramentas", False, INSTRUCAO_LONGA),
        ("instrução longa, COM ferramentas (hoje)", True, INSTRUCAO_LONGA),
    ]
    for nome, tools, instr in combos:
        t = await mede_adk(tools, instr)
        print(f"  {nome:38s} {t:>10.2f}s", flush=True)


asyncio.run(main())
