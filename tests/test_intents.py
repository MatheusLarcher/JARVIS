"""Unit: Intent Router + Context Engine + skills (HA mock). Sem servidor.

Uso: python tests/test_intents.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.context.engine import context_engine  # noqa: E402
from jarvis.intents.router import intent_router  # noqa: E402
from jarvis.skills.registry import skill_for  # noqa: E402

CASES = [
    ("liga a luz da sala", "light.turn_on", {"room": "sala"}),
    ("Jarvis, acende a luz do quarto", "light.turn_on", {"room": "quarto"}),
    ("liga a iluminação do escritório", "light.turn_on", {"room": "escritorio"}),
    ("desliga a luz da sala", "light.turn_off", {"room": "sala"}),
    ("apaga a luz", "light.turn_off", {}),
    ("liga a luz", "light.turn_on", {}),
    ("que horas são?", "info.time", {}),
    ("qual a temperatura?", "info.temperature", {}),
    ("me conta uma piada", None, {}),
    # cumprimentos: resposta pronta, sem passar por LLM nenhum
    ("bom dia", "social.greeting", {}),
    ("Bom dia, Jarvis", "social.greeting", {}),
    ("oi", "social.greeting", {}),
    ("boa noite", "social.greeting", {}),
    ("obrigado", "social.thanks", {}),
    ("valeu, Jarvis", "social.thanks", {}),
    ("tchau", "social.bye", {}),
    # ...mas cumprimento no meio de um pedido NÃO pode virar saudação
    ("bom dia, liga a luz da sala", "light.turn_on", {"room": "sala"}),
    ("como se diz bom dia em inglês", None, {}),
    # abrir programa existe desde 2026-08-11: agora este composto tem uma
    # segunda metade que É um pedido real, e ela tem que ser pega — mesmo
    # padrão do "bom dia, liga a luz da sala" logo acima
    ("obrigado por avisar, agora abre o navegador",
     "system.abrir_programa", {"programa": "o navegador"}),
]


async def main():
    fails = 0
    for text, want_intent, want_slots in CASES:
        m = intent_router.match(text)
        got = (m.intent_id if m else None, m.slots if m else {})
        ok = got == (want_intent, want_slots)
        fails += not ok
        print(("OK  " if ok else "FAIL"), repr(text), "->", got)

    # skill de luz com contexto: device no quarto, "liga a luz" sem cômodo
    ctx = context_engine.register("tablet-sala", {"device_type": "tablet"})
    ctx.room = "quarto"
    m = intent_router.match("liga a luz")
    r = await skill_for(m.intent_id).handle(m.intent_id, m.slots, ctx)
    print("OK  " if (r.ok and r.response_intent == "light_on_success") else "FAIL",
          "contexto quarto → liga luz do quarto:", r)
    fails += not r.ok

    # sem contexto de cômodo → pergunta
    ctx.room = None
    r2 = await skill_for(m.intent_id).handle(m.intent_id, {}, ctx)
    print("OK  " if r2.response_intent == "ambiguous_room" else "FAIL", "ambíguo:", r2)
    fails += r2.response_intent != "ambiguous_room"

    # hora e temperatura
    for phrase in ("que horas são", "qual a temperatura"):
        mm = intent_router.match(phrase)
        rr = await skill_for(mm.intent_id).handle(mm.intent_id, mm.slots, ctx)
        print("OK  " if rr.ok and rr.response_text else "FAIL", phrase, "->", rr.response_text)
        fails += not rr.ok

    print("\n" + ("TODOS OS TESTES PASSARAM" if fails == 0 else f"{fails} FALHAS"))
    sys.exit(1 if fails else 0)


asyncio.run(main())
