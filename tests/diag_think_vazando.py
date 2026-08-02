"""O raciocínio do modelo está vazando para a resposta falada?

Compara o texto que sai por três caminhos: chamada direta, chamada direta com
think desligado e o caminho real do JARVIS (ADK). Mostra o texto CRU, sem
filtro, pra ver de onde vem o excesso.

Uso: python tests/diag_think_vazando.py     (env jarvis)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.config import config  # noqa: E402

PERGUNTA = "quem foi santos dumont"


async def direto(com_think_off: bool) -> str:
    from litellm import acompletion
    cfg = config.settings["llm"]
    extras = {"api_base": cfg["api_base"], "max_tokens": cfg.get("max_tokens", 60)}
    if com_think_off:
        extras["think"] = False
    r = await acompletion(model=cfg["model"],
                          messages=[{"role": "user", "content": PERGUNTA}], **extras)
    msg = r.choices[0].message
    conteudo = (msg.content or "").strip()
    pensou = getattr(msg, "reasoning_content", None) or ""
    return f"content={conteudo!r}\n      reasoning={str(pensou)[:120]!r}"


async def pelo_jarvis() -> str:
    """Caminho real: ADK + agente configurado."""
    from jarvis.agents import agent
    from jarvis.context.engine import context_engine
    from jarvis.memory.db import store
    await store.open()
    ctx = context_engine.register("pc-matheus", {"device_type": "pc"})
    partes = [p async for p in agent.ask_stream(PERGUNTA, ctx)]
    await store.close()
    return "".join(partes).strip()


async def main():
    print(f"pergunta: {PERGUNTA!r}\n")
    print("1) chamada direta, SEM think=False:")
    print("     ", await direto(False))
    print("\n2) chamada direta, COM think=False:")
    print("     ", await direto(True))
    print("\n3) caminho real do JARVIS (o que vira fala):")
    texto = await pelo_jarvis()
    print(f"      {texto!r}")
    print(f"      ({len(texto.split())} palavras)")
    tem_think = "<think" in texto.lower() or "thinking" in texto.lower()
    print(f"      raciocínio vazando? {'SIM' if tem_think else 'não aparente'}")


asyncio.run(main())
