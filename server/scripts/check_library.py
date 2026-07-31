"""Confere a biblioteca de áudios: transcreve cada arquivo com o STT do próprio
JARVIS e compara com a frase que deveria ter sido dita.

Serve pra validar qualquer troca de voz — se o STT entende, o áudio está limpo.
Uso: python server/scripts/check_library.py
"""
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis.config import ROOT, config  # noqa: E402


def norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w\s]", "", t).strip()


def wer(ref: str, hyp: str) -> float:
    r, h = norm(ref).split(), norm(hyp).split()
    if not r:
        return 0.0
    d = np.zeros((len(r) + 1, len(h) + 1), dtype=int)
    d[:, 0] = np.arange(len(r) + 1)
    d[0, :] = np.arange(len(h) + 1)
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + cost)
    return d[len(r), len(h)] / len(r)


def load(path: Path) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1",
         "-ar", "16000", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def main():
    from jarvis.stt.nemotron import NemotronStt
    stt = NemotronStt()
    stt._load_sync()

    lib = ROOT / config.settings["tts"]["library_dir"]
    total, bad = 0, 0
    for intent, phrases in config.responses.items():
        for i, phrase in enumerate(phrases):
            files = list((lib / intent).glob(f"{i:02d}_{intent}.*"))
            if not files:
                print(f"[FALTA] {intent} #{i}: {phrase}")
                bad += 1
                continue
            got = stt.transcribe(load(files[0])) or ""
            e = wer(phrase, got)
            total += 1
            status = "ok  " if e <= 0.34 else "RUIM"
            if e > 0.34:
                bad += 1
            print(f"[{status}] {phrase!r} -> {got!r}  (WER {e:.2f})")
    print(f"\n{total - bad}/{total} arquivos entendidos corretamente.")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
