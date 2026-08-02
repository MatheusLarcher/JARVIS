"""Compara LLMs para o JARVIS: quanto tempo até a PRIMEIRA palavra (é o que
você sente) e se a resposta em português presta.

Mede o DeepSeek (API atual) e modelos locais em 4 bits.

Uso:
  python tests/bench_llm.py                      # deepseek (env jarvis)
  python tests/bench_llm.py Qwen/Qwen3-1.7B      # local (env jarvis-llm)
"""
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

PERGUNTAS = [
    "quem foi santos dumont",
    "me explica em uma frase o que e um buraco negro",
    "quantos minutos tem em duas horas e meia",
    "qual a capital da australia",
    "me da uma dica rapida pra dormir melhor",
]
INSTRUCAO = (
    "Você é o JARVIS, assistente pessoal do Matheus, em português do Brasil. "
    "Suas respostas são faladas em voz alta: responda em no máximo 2 frases "
    "curtas, direto ao ponto, sem markdown, sem listas e sem emojis."
)


def bench_configurado():
    """O que está configurado no settings.yml (hoje: Ollama local)."""
    import asyncio

    from jarvis.config import config
    from litellm import acompletion

    cfg = config.settings["llm"]
    modelo = cfg["model"]
    extras = {"api_base": cfg["api_base"]} if cfg.get("api_base") else {}

    async def uma(pergunta):
        t0 = time.perf_counter()
        primeiro = None
        partes = []
        resp = await acompletion(
            model=modelo,
            messages=[{"role": "system", "content": INSTRUCAO},
                      {"role": "user", "content": pergunta}],
            stream=True, max_tokens=120, **extras)
        async for pedaco in resp:
            texto = (pedaco.choices[0].delta.content or "")
            if texto and primeiro is None:
                primeiro = time.perf_counter() - t0
            partes.append(texto)
        return primeiro, time.perf_counter() - t0, "".join(partes).strip()

    async def todas():
        return [await uma(p) for p in PERGUNTAS]

    return modelo, asyncio.run(todas())


def bench_local(nome_modelo: str):
    """Modelo local em 4 bits, com streaming (pra medir a primeira palavra)."""
    from threading import Thread

    import torch
    from transformers import (AutoModelForCausalLM, AutoTokenizer,
                              BitsAndBytesConfig, TextIteratorStreamer)

    tok = AutoTokenizer.from_pretrained(nome_modelo)
    modelo = AutoModelForCausalLM.from_pretrained(
        nome_modelo, dtype=torch.bfloat16, device_map="cuda",
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True))
    modelo.eval()
    print(f"VRAM: {torch.cuda.memory_allocated() / 1024 ** 3:.2f} GB")

    resultados = []
    for pergunta in PERGUNTAS:
        mensagens = [{"role": "system", "content": INSTRUCAO},
                     {"role": "user", "content": pergunta}]
        extra = {"enable_thinking": False} if "qwen3" in nome_modelo.lower() else {}
        # o transformers 5 devolve dict aqui; versões antigas devolviam tensor
        entrada = tok.apply_chat_template(
            mensagens, add_generation_prompt=True, return_tensors="pt",
            return_dict=True, **extra)
        entrada = {k: v.to(modelo.device) for k, v in entrada.items()
                   if hasattr(v, "to")}
        streamer = TextIteratorStreamer(tok, skip_prompt=True,
                                        skip_special_tokens=True)
        t0 = time.perf_counter()
        Thread(target=modelo.generate, kwargs=dict(
            **entrada, max_new_tokens=120, do_sample=False,
            streamer=streamer)).start()
        primeiro, partes = None, []
        for pedaco in streamer:
            if pedaco and primeiro is None:
                primeiro = time.perf_counter() - t0
            partes.append(pedaco)
        resultados.append((primeiro, time.perf_counter() - t0,
                           "".join(partes).strip()))
    return nome_modelo, resultados


def main():
    alvo = sys.argv[1] if len(sys.argv) > 1 else "configurado"
    if alvo in ("configurado", "deepseek"):
        nome, resultados = bench_configurado()
    else:
        nome, resultados = bench_local(alvo)

    print(f"\n=== {nome} ===")
    primeiros, totais = [], []
    for pergunta, (p, t, texto) in zip(PERGUNTAS, resultados):
        primeiros.append(p or t)
        totais.append(t)
        print(f"\n  {pergunta}")
        print(f"    1ª palavra em {p:.2f}s | completa em {t:.2f}s")
        print(f"    {texto[:180]!r}")
    print(f"\n  MÉDIA: primeira palavra {np.mean(primeiros):.2f}s | "
          f"resposta completa {np.mean(totais):.2f}s")


main()
