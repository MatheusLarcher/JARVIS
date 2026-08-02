"""Descobre a forma certa de entregar o áudio ao Gemma 4.

Se o áudio entra mesmo, o prompt fica com MUITOS tokens (o encoder vira tokens de
áudio) e a transcrição volta certa. Se o áudio for ignorado, ficam poucos tokens e
a resposta é genérica.

Uso: python tests/diag_gemma_audio.py [forma]
     formas: posix | windows | uri | array
"""
import sys
from pathlib import Path

import torch

MODELO = "google/gemma-4-E2B-it"
WAV = Path(__file__).parent / ".cache" / "bench" / "gemma_1.wav"   # "liga a luz da sala"
PROMPT = ("Transcreva exatamente o que foi dito no áudio, em português. "
          "Responda apenas com a transcrição.")
FORMA = sys.argv[1] if len(sys.argv) > 1 else "posix"


def valor_audio():
    if FORMA == "windows":
        return str(WAV)
    if FORMA == "uri":
        return WAV.as_uri()
    if FORMA == "array":
        import librosa
        return librosa.load(str(WAV), sr=16000)[0]
    return WAV.as_posix()


def main():
    from transformers import AutoModelForMultimodalLM, AutoProcessor, BitsAndBytesConfig

    print(f"forma: {FORMA}", flush=True)
    processor = AutoProcessor.from_pretrained(MODELO)
    # carrega o modelo ANTES de preparar o áudio: o carregamento precisa de
    # bastante RAM e estourava se algo grande já estivesse na memória
    modelo = AutoModelForMultimodalLM.from_pretrained(
        MODELO, dtype=torch.bfloat16, device_map="cuda",
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True))
    modelo.eval()
    print("modelo ok", flush=True)

    # só o texto, pra saber quantos tokens o áudio acrescenta
    so_texto = processor.apply_chat_template(
        [{"role": "user", "content": [{"type": "text", "text": PROMPT}]}],
        add_generation_prompt=True, tokenize=True, return_dict=True,
        return_tensors="pt")
    n_texto = so_texto["input_ids"].shape[-1]

    entradas = processor.apply_chat_template(
        [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "audio", "audio": valor_audio()},
        ]}],
        add_generation_prompt=True, tokenize=True, return_dict=True,
        return_tensors="pt")
    n_audio = entradas["input_ids"].shape[-1]
    chaves = [k for k in entradas if k != "input_ids" and k != "attention_mask"]
    print(f"tokens: só texto={n_texto} | com áudio={n_audio} "
          f"(+{n_audio - n_texto}) | extras={chaves}", flush=True)
    if n_audio <= n_texto and not chaves:
        print(">>> o áudio NÃO entrou no prompt", flush=True)
        return

    entradas = entradas.to(modelo.device)
    with torch.inference_mode():
        saida = modelo.generate(**entradas, max_new_tokens=60, do_sample=False)
    texto = processor.decode(saida[0][n_audio:], skip_special_tokens=True).strip()
    print(f"esperado : 'Jarvis, liga a luz da sala.'", flush=True)
    print(f"transcreveu: {texto!r}", flush=True)


main()
