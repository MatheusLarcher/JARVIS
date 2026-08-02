"""Descobre como carregar e usar o Parakeet TDT nesta máquina.

Antes de medir, precisa funcionar. Este script tenta os caminhos possíveis
(transformers 5.x e NeMo), diz qual pegou e transcreve uma amostra do bench.

Roda no env que TIVER transformers >= 5.10 (aqui: jarvis-llm):
    ~/miniconda3/envs/jarvis-llm/python.exe tests/diag_parakeet.py
"""
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
AMOSTRA = AQUI / ".cache" / "bench" / "n0.wav"          # "Jarvis, liga a luz da sala."
MODELO = "nvidia/parakeet-tdt-0.6b-v3"


def carregar_audio(p: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p),
                          "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def versoes():
    import torch
    import transformers
    print(f"transformers {transformers.__version__} | torch {torch.__version__} | "
          f"cuda {torch.cuda.is_available()}")


def via_transformers(audio):
    """Caminho novo: o Parakeet entrou no transformers 5.x."""
    import torch
    from transformers import AutoModelForCTC, AutoProcessor

    t0 = time.monotonic()
    proc = AutoProcessor.from_pretrained(MODELO)
    modelo = AutoModelForCTC.from_pretrained(MODELO)
    if torch.cuda.is_available():
        modelo = modelo.cuda()
    modelo.eval()
    print(f"    carregou em {time.monotonic() - t0:.1f}s")

    entradas = proc(audio, sampling_rate=16000, return_tensors="pt")
    entradas = {k: (v.cuda() if torch.cuda.is_available() and hasattr(v, "cuda") else v)
                for k, v in entradas.items()}
    t0 = time.monotonic()
    with torch.no_grad():
        saida = modelo.generate(**entradas)
    texto = proc.batch_decode(saida)
    print(f"    transcreveu em {time.monotonic() - t0:.2f}s")
    return texto[0] if isinstance(texto, list) else texto


def via_pipeline(audio):
    """Fallback: pipeline de ASR do transformers."""
    import torch
    from transformers import pipeline

    t0 = time.monotonic()
    pipe = pipeline("automatic-speech-recognition", model=MODELO,
                    device=0 if torch.cuda.is_available() else -1)
    print(f"    carregou em {time.monotonic() - t0:.1f}s")
    t0 = time.monotonic()
    r = pipe({"raw": audio, "sampling_rate": 16000})
    print(f"    transcreveu em {time.monotonic() - t0:.2f}s")
    return r.get("text") if isinstance(r, dict) else r


def via_nemo(audio):
    """Caminho antigo: NeMo (precisa de transformers 4.x, provavelmente falha aqui)."""
    import nemo.collections.asr as nemo_asr
    import torch

    t0 = time.monotonic()
    m = nemo_asr.models.ASRModel.from_pretrained(MODELO)
    if torch.cuda.is_available():
        m = m.cuda()
    m.eval()
    print(f"    carregou em {time.monotonic() - t0:.1f}s")
    t0 = time.monotonic()
    out = m.transcribe([audio], verbose=False)
    print(f"    transcreveu em {time.monotonic() - t0:.2f}s")
    primeiro = out[0] if out else ""
    return getattr(primeiro, "text", primeiro if isinstance(primeiro, str) else "")


def main():
    versoes()
    if not AMOSTRA.is_file():
        print(f"não achei {AMOSTRA} — rode tests/bench_stt.py uma vez pra gerar")
        return 2
    audio = carregar_audio(AMOSTRA)
    print(f"amostra: {AMOSTRA.name} ({len(audio) / 16000:.1f}s)")
    print('esperado: "Jarvis, liga a luz da sala."\n')

    for nome, fn in (("transformers (AutoModelForCTC)", via_transformers),
                     ("transformers (pipeline)", via_pipeline),
                     ("NeMo", via_nemo)):
        print(f"--- {nome} ---")
        try:
            texto = fn(audio)
            print(f"    RESULTADO: {texto!r}\n")
            if texto:
                print(f"FUNCIONOU pelo caminho: {nome}")
                return 0
        except Exception as e:
            print(f"    falhou: {type(e).__name__}: {str(e)[:160]}\n")
    print("nenhum caminho funcionou")
    return 1


sys.exit(main())
