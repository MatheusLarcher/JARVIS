"""Como desligar o "pensar antes de responder" do Qwen3.5 passando pelo LiteLLM.

Sem isso o modelo gasta a resposta inteira pensando e devolve texto VAZIO.
Direto na API do Ollama funciona com think=false; aqui descobrimos qual jeito
o LiteLLM repassa esse parâmetro.

Uso: python tests/diag_ollama_nothink.py     (env jarvis)
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

MODELO = "ollama_chat/qwen3.5:0.8b"
BASE = "http://127.0.0.1:11434"
PERGUNTA = "responda em uma frase: qual a capital da australia"

TENTATIVAS = {
    "sem nada": {},
    "think=False": {"think": False},
    "extra_body think": {"extra_body": {"think": False}},
    "chat_template_kwargs": {"chat_template_kwargs": {"enable_thinking": False}},
    "options think": {"options": {"think": False}},
}


async def main():
    from litellm import acompletion

    for nome, extra in TENTATIVAS.items():
        t0 = time.perf_counter()
        try:
            r = await acompletion(
                model=MODELO, api_base=BASE,
                messages=[{"role": "user", "content": PERGUNTA}],
                max_tokens=120, **extra)
            texto = (r.choices[0].message.content or "").strip()
            dt = time.perf_counter() - t0
            marca = "RESPONDEU" if texto else "VAZIO"
            print(f"  {nome:22s} {dt:5.2f}s  {marca:9s} {texto[:70]!r}")
        except Exception as e:
            print(f"  {nome:22s} falhou: {type(e).__name__}: {str(e)[:80]}")


asyncio.run(main())
