"""Compara modelos de STT em português: qualidade (WER) e velocidade.

Gera frases de teste com vozes diferentes (algumas com ruído de fundo, como na vida
real), transcreve com cada motor e mostra uma tabela comparativa.

Uso:
  python tests/bench_stt.py                 # todos os motores instalados
  python tests/bench_stt.py nemotron        # só um
"""
import asyncio
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
CACHE = Path(__file__).parent / ".cache" / "bench"

FRASES = [
    "Jarvis, liga a luz da sala.",
    "Jarvis, desliga a luz do quarto.",
    "Jarvis, que horas são?",
    "Jarvis, qual a temperatura aqui dentro?",
    "Jarvis, me conta uma curiosidade sobre o espaço.",
    "Liga a iluminação do escritório, Jarvis.",
    "Jarvis, acende a luz da cozinha por favor.",
    "Jarvis, coloca uma música tranquila para trabalhar.",
]
VOZES = ["pt-BR-AntonioNeural", "pt-BR-FranciscaNeural", "pt-BR-ThalitaMultilingualNeural"]


def norm(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w\s]", " ", t).split()


def wer(ref: str, hyp: str) -> float:
    r, h = norm(ref), norm(hyp)
    if not r:
        return 0.0
    d = np.zeros((len(r) + 1, len(h) + 1), dtype=int)
    d[:, 0] = np.arange(len(r) + 1)
    d[0, :] = np.arange(len(h) + 1)
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1,
                          d[i - 1, j - 1] + (r[i - 1] != h[j - 1]))
    return d[len(r), len(h)] / len(r)


async def preparar() -> list[tuple[str, Path]]:
    """Gera os áudios de teste: limpos e com ruído/volume baixo."""
    import edge_tts
    CACHE.mkdir(parents=True, exist_ok=True)
    amostras = []
    for i, frase in enumerate(FRASES):
        voz = VOZES[i % len(VOZES)]
        mp3 = CACHE / f"{i}.mp3"
        if not mp3.exists():
            await edge_tts.Communicate(frase, voz).save(str(mp3))
        wav = CACHE / f"{i}.wav"
        if not wav.exists():
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3),
                            "-ac", "1", "-ar", "16000", str(wav)], check=True)
        amostras.append((frase, wav))

        # versão "sala real": mais baixa e com chiado
        ruido = CACHE / f"{i}_ruido.wav"
        if not ruido.exists():
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", str(wav),
                 "-af", "volume=0.35,aecho=0.6:0.35:60:0.25,"
                        "highpass=f=90,lowpass=f=7000",
                 "-ac", "1", "-ar", "16000", str(ruido)], check=True)
        amostras.append((frase, ruido))
    return amostras


def carregar(pcm_path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(pcm_path),
                          "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


# ----------------------------------------------------------------- motores
def motor_nemotron():
    from jarvis.stt.nemotron import NemotronStt
    stt = NemotronStt()
    stt._load_sync()
    return lambda audio: stt.transcribe(audio)


def motor_parakeet():
    """nvidia/parakeet-tdt-0.6b-v3 — multilíngue, inclui português."""
    import nemo.collections.asr as nemo_asr
    import torch
    m = nemo_asr.models.ASRModel.from_pretrained("nvidia/parakeet-tdt-0.6b-v3")
    if torch.cuda.is_available():
        m = m.cuda()
    m.eval()

    def go(audio):
        out = m.transcribe([audio], verbose=False)
        if not out:
            return ""
        first = out[0]
        return getattr(first, "text", first if isinstance(first, str) else "")
    return go


def motor_whisper():
    """faster-whisper large-v3-turbo."""
    from faster_whisper import WhisperModel
    m = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")

    def go(audio):
        segs, _ = m.transcribe(audio, language="pt", beam_size=5)
        return " ".join(s.text for s in segs)
    return go


def motor_canary():
    """nvidia/canary-1b-v2 — encoder-decoder, costuma ir muito bem em PT."""
    import nemo.collections.asr as nemo_asr
    import torch
    m = nemo_asr.models.ASRModel.from_pretrained("nvidia/canary-1b-v2")
    if torch.cuda.is_available():
        m = m.cuda()
    m.eval()

    def go(audio):
        try:
            out = m.transcribe([audio], source_lang="pt", target_lang="pt", verbose=False)
        except TypeError:
            out = m.transcribe([audio], verbose=False)
        if not out:
            return ""
        first = out[0]
        return getattr(first, "text", first if isinstance(first, str) else "")
    return go


MOTORES = {"nemotron": motor_nemotron, "parakeet": motor_parakeet,
           "canary": motor_canary, "whisper": motor_whisper}


async def main():
    quais = sys.argv[1:] or list(MOTORES)
    amostras = await preparar()
    print(f"{len(amostras)} amostras ({len(FRASES)} frases: limpa + com ruído)\n")

    resultados = {}
    for nome in quais:
        if nome not in MOTORES:
            continue
        print(f"--- carregando {nome} ---")
        try:
            t0 = time.monotonic()
            transcrever = MOTORES[nome]()
            carga = time.monotonic() - t0
        except Exception as e:
            print(f"    indisponível: {type(e).__name__}: {str(e)[:120]}\n")
            continue

        erros_limpo, erros_ruido, tempos = [], [], []
        for idx, (frase, wav) in enumerate(amostras):
            audio = carregar(wav)
            t0 = time.monotonic()
            texto = transcrever(audio) or ""
            tempos.append(time.monotonic() - t0)
            e = wer(frase, texto)
            (erros_ruido if "ruido" in wav.name else erros_limpo).append(e)
            if idx < 4:
                print(f"    {frase!r}\n      -> {texto.strip()!r} (WER {e:.2f})")
        resultados[nome] = {
            "limpo": float(np.mean(erros_limpo)),
            "ruido": float(np.mean(erros_ruido)),
            "tempo": float(np.mean(tempos)),
            "carga": carga,
        }
        print()

    print("\n===== RESULTADO =====")
    print(f"{'motor':12s} {'WER limpo':>10s} {'WER ruído':>10s} {'s/frase':>9s} {'carga(s)':>9s}")
    for nome, r in sorted(resultados.items(), key=lambda x: x[1]["limpo"] + x[1]["ruido"]):
        print(f"{nome:12s} {r['limpo']:10.3f} {r['ruido']:10.3f} "
              f"{r['tempo']:9.2f} {r['carga']:9.1f}")
    print("\n(WER menor = melhor; 0.00 = transcrição perfeita)")


asyncio.run(main())
