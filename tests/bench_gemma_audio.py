"""Mede o Gemma 4 E2B respondendo direto do ÁUDIO (sem transcrever antes).

O que interessa saber antes de trocar o pipeline:
  - cabe na GPU junto com o resto? (VRAM)
  - quanto tempo até a resposta? (é o motivo da troca)
  - entende português de verdade?
  - consegue decidir chamar ferramenta (ligar a luz)?

Uso: python tests/bench_gemma_audio.py     (env jarvis-llm)
"""
import gc
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch

MODELO = "google/gemma-4-E2B-it"
CACHE = Path(__file__).parent / ".cache" / "bench"

PEDIDOS = [
    "Jarvis, me explica em uma frase o que é um buraco negro.",
    "Jarvis, liga a luz da sala.",
    "Jarvis, que dia é hoje?",
    "Jarvis, quantos minutos tem em duas horas e meia?",
]

INSTRUCAO = (
    "Você é o JARVIS, assistente pessoal do Matheus, em português do Brasil. "
    "Responda em no máximo 2 frases curtas, direto ao ponto, sem markdown. "
    "Se o pedido for para controlar a casa (luz, temperatura), responda APENAS "
    "com uma linha no formato: ACAO: <ligar|desligar> <comodo>"
)

# com --transcrever, só pedimos a transcrição: é o teste que mostra se ele
# realmente ENTENDE o áudio em português (e não se está respondendo no vácuo)
TRANSCREVER = (
    "Transcreva exatamente o que foi dito no áudio, em português. "
    "Responda apenas com a transcrição, sem comentários."
)


def vram_gb():
    if not torch.cuda.is_available():
        return 0.0
    return torch.cuda.memory_allocated() / 1024 ** 3


def prepara_audios() -> list[tuple[str, Path]]:
    import asyncio

    import edge_tts
    CACHE.mkdir(parents=True, exist_ok=True)
    saida = []
    for i, texto in enumerate(PEDIDOS):
        mp3 = CACHE / f"gemma_{i}.mp3"
        wav = CACHE / f"gemma_{i}.wav"
        if not wav.exists():
            if not mp3.exists():
                asyncio.run(edge_tts.Communicate(texto, "pt-BR-AntonioNeural").save(str(mp3)))
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3),
                            "-ac", "1", "-ar", "16000", str(wav)], check=True)
        saida.append((texto, wav))
    return saida


def main():
    amostras = prepara_audios()
    print(f"modelo: {MODELO}\n")

    # tem que ser MultimodalLM: com AutoModelForCausalLM o áudio é ignorado e
    # ele responde no vácuo ("Entendido. Qual é a sua solicitação?")
    from transformers import AutoModelForMultimodalLM, AutoProcessor
    AutoModelForCausalLM = AutoModelForMultimodalLM

    # o E2B tem ~9,6 GB em bf16 e a placa aqui tem 8 GB (com o servidor usando
    # parte dela), então o padrão é 4 bits; "--bf16" força precisão cheia
    quatro_bits = "--bf16" not in sys.argv
    t0 = time.monotonic()
    processor = AutoProcessor.from_pretrained(MODELO)
    if quatro_bits:
        from transformers import BitsAndBytesConfig
        qcfg = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            # quantizar o encoder de áudio destrói o entendimento da fala:
            # o modelo passa a responder "não sei o que foi dito no áudio"
            llm_int8_skip_modules=["audio_tower", "vision_tower",
                                   "embed_audio", "embed_vision", "lm_head"],
        )
        modelo = AutoModelForCausalLM.from_pretrained(
            MODELO, dtype=torch.bfloat16, device_map="cuda",
            quantization_config=qcfg)
        print("carregando em 4 bits")
    else:
        # bf16 não cabe inteiro em 8 GB: deixa o accelerate mandar o excedente
        # pra CPU. Fica lento, mas serve pra avaliar a QUALIDADE sem quantização.
        modelo = AutoModelForCausalLM.from_pretrained(
            MODELO, dtype=torch.bfloat16, device_map="auto",
            max_memory={0: "6GiB", "cpu": "24GiB"})
        print("carregando em bf16 (parte na CPU)")
    modelo.eval()
    carga = time.monotonic() - t0
    print(f"carregado em {carga:.1f}s | VRAM ocupada: {vram_gb():.2f} GB\n")

    tempos = []
    for texto, wav in amostras:
        # o texto vem ANTES do áudio, como manda o card do modelo
        pedido = TRANSCREVER if "--transcrever" in sys.argv else INSTRUCAO
        mensagens = [
            {"role": "user", "content": [
                {"type": "text", "text": pedido},
                {"type": "audio", "audio": wav.as_posix()},
            ]},
        ]
        entradas = processor.apply_chat_template(
            mensagens, add_generation_prompt=True, tokenize=True,
            return_dict=True, return_tensors="pt").to(modelo.device)

        t0 = time.monotonic()
        with torch.inference_mode():
            saida = modelo.generate(**entradas, max_new_tokens=80, do_sample=False)
        dt = time.monotonic() - t0
        tempos.append(dt)
        resposta = processor.decode(
            saida[0][entradas["input_ids"].shape[-1]:], skip_special_tokens=True).strip()
        print(f"  falado : {texto}")
        print(f"  ouviu e respondeu em {dt:.2f}s: {resposta!r}\n")

    print(f"média por pedido: {np.mean(tempos):.2f}s")
    print(f"VRAM no pico: {torch.cuda.max_memory_allocated() / 1024 ** 3:.2f} GB")

    del modelo
    gc.collect()
    torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
