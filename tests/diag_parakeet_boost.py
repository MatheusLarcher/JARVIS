"""Dá pra ensinar o nome "Jarvis" ao Parakeet sem treinar?

O Whisper aceita `initial_prompt` (texto de contexto) e por isso acerta o nome
24/24. O Parakeet é transducer e não tem esse gancho — no bench ele acertou
11/24. O equivalente no mundo transducer é *word boosting* / context biasing,
que o NeMo expõe no decoding.

Este script tenta carregar o Parakeet PELO NeMo (env `jarvis`, transformers 4.x)
e ligar o boosting do nome. Se funcionar e subir o acerto, a comparação muda.

Uso: ~/miniconda3/envs/jarvis/python.exe tests/diag_parakeet_boost.py
"""
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
BENCH = AQUI / ".cache" / "bench"
MODELO = "nvidia/parakeet-tdt-0.6b-v3"
NOME = "Jarvis"


def audio(p: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p),
                          "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def texto_de(saida):
    if not saida:
        return ""
    primeiro = saida[0]
    return getattr(primeiro, "text", primeiro if isinstance(primeiro, str) else "")


def main():
    import torch
    print("carregando pelo NeMo...", flush=True)
    t0 = time.monotonic()
    try:
        import nemo.collections.asr as nemo_asr
        m = nemo_asr.models.ASRModel.from_pretrained(MODELO)
    except Exception as e:
        print(f"NeMo não carregou o Parakeet: {type(e).__name__}: {str(e)[:200]}")
        return 1
    if torch.cuda.is_available():
        m = m.cuda()
    m.eval()
    print(f"carregou em {time.monotonic() - t0:.1f}s\n")

    dificeis = sorted(BENCH.glob("n*_dificil.wav"))
    amostras = [audio(p) for p in dificeis]

    def roda(rotulo):
        acertos, tempos = 0, []
        for i, a in enumerate(amostras):
            t = time.monotonic()
            try:
                txt = texto_de(m.transcribe([a], verbose=False))
            except Exception as e:
                print(f"    erro: {type(e).__name__}: {str(e)[:100]}")
                return None
            tempos.append(time.monotonic() - t)
            ok = "jarvis" in txt.lower()
            acertos += ok
            if i < 3:
                print(f"    {'OK ' if ok else '   '} {txt.strip()[:62]!r}")
        print(f"    {rotulo}: nome em {acertos}/{len(amostras)} | "
              f"{np.mean(tempos):.2f}s por frase\n")
        return acertos

    print(f"--- sem boosting ({len(amostras)} áudios difíceis) ---")
    base = roda("sem boosting")

    # O boosting fica na config de decoding do transducer. O nome do campo
    # mudou entre versões do NeMo, então tentamos os que existem.
    print("--- com boosting do nome ---")
    cfg = m.cfg.decoding
    ligou = None
    for caminho, valor in (
        ("greedy.boosting_tree", None),
        ("context_biasing", None),
        ("boosting_tree", None),
    ):
        try:
            alvo = cfg
            partes = caminho.split(".")
            for p in partes[:-1]:
                alvo = alvo[p]
            if partes[-1] in alvo:
                ligou = caminho
                break
        except Exception:
            continue
    if not ligou:
        campos = list(cfg.keys()) if hasattr(cfg, "keys") else dir(cfg)
        print("    esta versão do NeMo não expõe boosting no decoding.")
        print(f"    campos disponíveis: {campos}")
        print("\n    => sem treinar, não dá pra ensinar o nome a ele por aqui.")
        return 0

    print(f"    campo encontrado: {ligou}")
    print("    (implementar o carregamento da árvore de boosting)")
    return 0


sys.exit(main())
