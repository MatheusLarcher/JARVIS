"""Toda resposta falada tem que terminar com `speak_end`.

O device liga o "estou falando" no `speak` de seq 0 e só desliga no
`speak_end`. Sem ele, a janela do PC fica presa na tela, opaca, até a próxima
interação — e isso acontecia justamente nas respostas mais comuns, as prontas
da biblioteca ("Pronto.", "Bom dia.").

Roda sem GPU, sem servidor e sem LLM: as camadas caras são substituídas.
Uso: python tests/test_fim_da_fala.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.agents import roteador  # noqa: E402
from jarvis.context.engine import context_engine  # noqa: E402
from jarvis.gateway import dialog as dialog_mod  # noqa: E402
from jarvis.memory.db import store  # noqa: E402
from jarvis.skills.base import SkillResult  # noqa: E402


class FakeSkill:
    def __init__(self, resultado):
        self.resultado = resultado

    async def handle(self, intent_id, slots, ctx):
        return self.resultado


async def roda(frase, *, skill=None, decisao=None, resposta_agente=""):
    """Executa on_final com as camadas caras trocadas e devolve os eventos."""
    eventos = []

    async def send(msg):
        eventos.append(msg)

    d = dialog_mod.DialogManager("teste-fim", send)
    d.start_interaction()

    # TTS e biblioteca: não geram áudio, só registram que falariam
    async def fake_tts(texto):
        d._falou = True
        await send({"type": "speak", "text": texto, "seq": d._proximo_seq()})

    async def fake_lib(intent):
        texto = f"[{intent}]"
        await fake_tts(texto)
        return texto

    d._speak_tts = fake_tts
    d._speak_library = fake_lib

    orig_skill = dialog_mod.skill_for
    orig_match = dialog_mod.intent_router.match
    orig_decidir = roteador.decidir
    orig_stream = d._falar_em_stream
    try:
        if skill is not None:
            dialog_mod.intent_router.match = lambda t: type(
                "M", (), {"intent_id": "teste.intent", "slots": {}})()
            dialog_mod.skill_for = lambda i: skill
        else:
            dialog_mod.intent_router.match = lambda t: None

        async def fake_decidir(t):
            return decisao, 0.01
        roteador.decidir = fake_decidir
        dialog_mod.agent_roteador.decidir = fake_decidir

        async def fake_stream(ctx, agente=None):
            if resposta_agente:
                await fake_tts(resposta_agente)
            return resposta_agente
        d._falar_em_stream = fake_stream

        await d.on_final(frase)
    finally:
        dialog_mod.skill_for = orig_skill
        dialog_mod.intent_router.match = orig_match
        roteador.decidir = orig_decidir
        dialog_mod.agent_roteador.decidir = orig_decidir
        d._falar_em_stream = orig_stream
    return eventos


def confere(nome, eventos):
    """Se falou (mandou algum speak), tem que ter mandado UM speak_end depois."""
    falas = [i for i, e in enumerate(eventos) if e["type"] == "speak"]
    fins = [i for i, e in enumerate(eventos) if e["type"] == "speak_end"]
    if not falas:
        ok = not fins
        motivo = "não falou nada e não mandou speak_end"
    else:
        ok = len(fins) == 1 and fins[0] > falas[-1]
        motivo = (f"{len(falas)} fala(s), {len(fins)} speak_end"
                  + ("" if ok else " ← DEVIA SER 1, DEPOIS DA ÚLTIMA FALA"))
    print(("OK  " if ok else "FAIL"), f"{nome:38s} {motivo}")
    return ok


async def main():
    await store.open()
    context_engine.register("teste-fim", {"device_type": "web"})
    Decisao = roteador.Decisao
    resultados = []

    resultados.append(confere("skill com áudio pronto", await roda(
        "liga a luz da sala",
        skill=FakeSkill(SkillResult(ok=True, response_intent="light_on_success")))))

    resultados.append(confere("cumprimento (saudação pronta)", await roda(
        "bom dia",
        skill=FakeSkill(SkillResult(ok=True, response_intent="saudacao_manha")))))

    resultados.append(confere("skill com texto dinâmico", await roda(
        "que horas são",
        skill=FakeSkill(SkillResult(ok=True, response_text="São nove horas.")))))

    resultados.append(confere("skill que falhou", await roda(
        "liga a luz",
        skill=FakeSkill(SkillResult(ok=False, response_intent="error",
                                    error="sensor fora")))))

    resultados.append(confere("roteador respondeu direto", await roda(
        "oi", decisao=Decisao(resposta="Olá."))))

    resultados.append(confere("agente respondeu", await roda(
        "quem foi santos dumont", decisao=Decisao(agente="conversa"),
        resposta_agente="Foi um pioneiro da aviação.")))

    resultados.append(confere("agente ficou mudo", await roda(
        "pergunta difícil", decisao=Decisao(agente="conversa"),
        resposta_agente="")))

    # o registro roda em segundo plano de propósito; espera antes de fechar o banco
    pendentes = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pendentes:
        await asyncio.gather(*pendentes, return_exceptions=True)
    await store.close()
    print("\n" + ("TODOS OS TESTES PASSARAM" if all(resultados)
                  else f"{resultados.count(False)} FALHAS"))
    sys.exit(0 if all(resultados) else 1)


asyncio.run(main())
