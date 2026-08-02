"""Compara modelos de transcrição no que importa pro JARVIS.

Três coisas são medidas separadamente, porque servem a propósitos diferentes:
  1. acertou o NOME? (é o que dispara o assistente — se erra, ele te ignora)
  2. acertou o COMANDO? (o resto da frase, que vira ação)
  3. quanto tempo levou? (velocidade é prioridade neste projeto)

Cada frase é testada limpa e numa versão "sala real" (mais baixa, com eco).

Uso:
  python tests/bench_stt.py                  # todos os motores
  python tests/bench_stt.py whisper_hot      # só um
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

# frases reais de uso, sempre com o nome (é o caso que importa)
FRASES = [
    "Jarvis, liga a luz da sala.",
    "Jarvis, desliga a luz do quarto.",
    "Jarvis, que horas são?",
    "Jarvis, qual a temperatura aqui dentro?",
    "Jarvis, acende a luz da cozinha por favor.",
    "Jarvis, me conta uma curiosidade sobre o espaço.",
    "Jarvis, abre o navegador.",
    "Liga a iluminação do escritório, Jarvis.",
]
VOZES = ["pt-BR-AntonioNeural", "pt-BR-FranciscaNeural", "pt-BR-ThalitaMultilingualNeural"]
NOME = "jarvis"


def norm(t: str) -> list[str]:
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


def acertou_nome(hyp: str) -> bool:
    """O nome saiu escrito certo? (não vale 'Já Luiz', 'Jairus'...)"""
    return NOME in " ".join(norm(hyp))


def so_comando(frase: str) -> str:
    """A frase sem o nome — é o que vira ação."""
    palavras = [p for p in norm(frase) if p != NOME]
    return " ".join(palavras)


def reconheceu_chamada(hyp: str) -> bool:
    """O JARVIS acordaria com essa transcrição? (usa o matcher de verdade)"""
    from jarvis.audio.wakeword import matcher
    return matcher.match(hyp)[0]


async def preparar() -> list[tuple[str, Path, str]]:
    import edge_tts
    CACHE.mkdir(parents=True, exist_ok=True)
    amostras = []
    for i, frase in enumerate(FRASES):
        voz = VOZES[i % len(VOZES)]
        mp3 = CACHE / f"n{i}.mp3"
        if not mp3.exists():
            await edge_tts.Communicate(frase, voz).save(str(mp3))
        wav = CACHE / f"n{i}.wav"
        if not wav.exists():
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3),
                            "-ac", "1", "-ar", "16000", str(wav)], check=True)
        amostras.append((frase, wav, "limpo"))

        ruido = CACHE / f"n{i}_ruido.wav"
        if not ruido.exists():
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", str(wav),
                 "-af", "volume=0.35,aecho=0.6:0.35:60:0.25,highpass=f=90,lowpass=f=7000",
                 "-ac", "1", "-ar", "16000", str(ruido)], check=True)
        amostras.append((frase, ruido, "ruido"))

        # "microfone do outro lado da sala": bem mais baixo, com reverberação
        # e chiado de fundo — é onde o modelo costuma errar o nome
        dificil = CACHE / f"n{i}_dificil.wav"
        if not dificil.exists():
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", str(wav),
                 "-f", "lavfi", "-i", "anoisesrc=color=pink:amplitude=0.02:r=16000",
                 "-filter_complex",
                 "[0:a]volume=0.18,aecho=0.8:0.7:120|200:0.5|0.3,"
                 "highpass=f=140,lowpass=f=5200[v];[v][1:a]amix=inputs=2:duration=first",
                 "-ac", "1", "-ar", "16000", str(dificil)], check=True)
        amostras.append((frase, dificil, "dificil"))
    return amostras


def carregar(p: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p),
                          "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


# ----------------------------------------------------------------- motores
def motor_nemotron():
    from jarvis.stt.nemotron import NemotronStt
    stt = NemotronStt()
    stt._load_sync()
    return stt.transcribe


def _whisper(tamanho: str, hotwords=False, prompt=False, beam=1):
    """hotwords e initial_prompt são medidos SEPARADOS: um deles custa caro."""
    from faster_whisper import WhisperModel

    from jarvis.stt.whisper import _hotwords_padrao
    m = WhisperModel(tamanho, device="cuda", compute_type="float16")
    hot = _hotwords_padrao() if hotwords else None
    ctx = ("Conversa com o assistente de voz Jarvis. "
           "Exemplos: Jarvis, liga a luz da sala. Jarvis, que horas são?"
           ) if prompt else None

    def go(audio):
        segs, _ = m.transcribe(audio, language="pt", beam_size=beam,
                               vad_filter=False, condition_on_previous_text=False,
                               initial_prompt=ctx, hotwords=hot)
        return " ".join(s.text for s in segs).strip()
    return go


def motor_whisper():
    return _whisper("large-v3-turbo")


def motor_whisper_hot():
    """como está no código hoje: hotwords + prompt"""
    return _whisper("large-v3-turbo", hotwords=True, prompt=True)


def motor_whisper_so_hot():
    return _whisper("large-v3-turbo", hotwords=True)


def motor_whisper_so_prompt():
    return _whisper("large-v3-turbo", prompt=True)


def motor_whisper_small():
    return _whisper("small")


def motor_whisper_small_hot():
    return _whisper("small", hotwords=True)


def motor_canary():
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


MOTORES = {
    "nemotron": motor_nemotron,
    "whisper_turbo": motor_whisper,
    "whisper_hot": motor_whisper_hot,
    "whisper_so_hot": motor_whisper_so_hot,
    "whisper_so_prompt": motor_whisper_so_prompt,
    "whisper_small": motor_whisper_small,
    "whisper_small_hot": motor_whisper_small_hot,
    "canary": motor_canary,
}


async def main():
    quais = sys.argv[1:] or list(MOTORES)
    amostras = await preparar()
    print(f"{len(amostras)} amostras ({len(FRASES)} frases x limpo/ruído)\n")

    resultados = {}
    for nome in quais:
        if nome not in MOTORES:
            continue
        print(f"--- {nome} ---", flush=True)
        try:
            t0 = time.monotonic()
            transcrever = MOTORES[nome]()
            carga = time.monotonic() - t0
        except Exception as e:
            print(f"    indisponível: {type(e).__name__}: {str(e)[:120]}\n")
            continue

        r = {"carga": carga, "tempo": [], "nome_ok": 0, "acorda": 0, "total": 0,
             "cmd": {"limpo": [], "ruido": [], "dificil": []},
             "acorda_por_tipo": {"limpo": 0, "ruido": 0, "dificil": 0},
             "por_tipo": {"limpo": 0, "ruido": 0, "dificil": 0}}
        for frase, wav, tipo in amostras:
            audio = carregar(wav)
            t0 = time.monotonic()
            texto = transcrever(audio) or ""
            r["tempo"].append(time.monotonic() - t0)
            r["total"] += 1
            r["por_tipo"][tipo] += 1
            r["nome_ok"] += acertou_nome(texto)
            acorda = reconheceu_chamada(texto)
            r["acorda"] += acorda
            r["acorda_por_tipo"][tipo] += acorda
            hyp_cmd = " ".join(p for p in norm(texto) if p != NOME)
            r["cmd"][tipo].append(wer(so_comando(frase), hyp_cmd))
            if tipo == "dificil" and len(r["cmd"]["dificil"]) <= 3:
                print(f"    [difícil] {texto.strip()!r}", flush=True)
        resultados[nome] = r
        print()

    print("\n================ RESULTADO ================")
    print(f"{'motor':20s} {'nome ok':>9s} {'acorda':>8s} "
          f"{'cmd limpo':>10s} {'cmd ruído':>10s} {'cmd difícil':>12s} "
          f"{'s/frase':>8s} {'carga':>7s}")
    ordem = sorted(resultados.items(),
                   key=lambda x: (-x[1]["acorda"],
                                  np.mean(sum(x[1]["cmd"].values(), []))))
    for nome, r in ordem:
        print(f"{nome:20s} {r['nome_ok']:>5d}/{r['total']:<3d} "
              f"{r['acorda']:>5d}/{r['total']:<2d} "
              f"{np.mean(r['cmd']['limpo']):>10.3f} "
              f"{np.mean(r['cmd']['ruido']):>10.3f} "
              f"{np.mean(r['cmd']['dificil']):>12.3f} "
              f"{np.mean(r['tempo']):>8.2f} {r['carga']:>7.1f}")

    print("\n--- acorda o JARVIS por condição de áudio ---")
    print(f"{'motor':20s} {'limpo':>8s} {'ruído':>8s} {'difícil':>9s}")
    for nome, r in ordem:
        t = r["por_tipo"]
        a = r["acorda_por_tipo"]
        print(f"{nome:20s} {a['limpo']:>4d}/{t['limpo']:<3d} "
              f"{a['ruido']:>4d}/{t['ruido']:<3d} {a['dificil']:>5d}/{t['dificil']:<3d}")

    print("\nnome ok = escreveu 'Jarvis' certo | acorda = o matcher reconheceria a chamada")
    print("cmd = erro só no comando (sem o nome); menor é melhor")


asyncio.run(main())
