"""Gera os áudios da biblioteca de respostas (config/responses.yml) com o TTS configurado.

Uso:
  python server/scripts/build_library.py              # só o que falta
  python server/scripts/build_library.py --force      # regera tudo (troca de voz)
  python server/scripts/build_library.py --force --verify
      gera até N tentativas por frase e fica com a que o STT do JARVIS entende
      melhor — a voz clonada às vezes engasga em frases muito curtas.
"""
import asyncio
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis.config import ROOT, config  # noqa: E402
from jarvis.tts.engine import tts  # noqa: E402

ATTEMPTS = 4
WER_OK = 0.34


def _load16k(path: Path) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1",
         "-ar", "16000", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


async def best_take(phrase: str, stt, attempts: int = ATTEMPTS) -> Path | None:
    """Gera algumas vezes e devolve a melhor tomada segundo o STT."""
    from check_library import wer
    best, best_err = None, 9.9
    for attempt in range(attempts):
        # varia um pouco a cada tentativa pra não repetir o mesmo erro
        path = await tts.synthesize_fresh(
            phrase,
            temperature=0.7 + 0.1 * attempt,
            cfg_weight=0.5 + 0.1 * attempt,
        )
        if not path:
            continue
        got = stt.transcribe(_load16k(path)) or ""
        err = wer(phrase, got)
        if err < best_err:
            best, best_err = path.read_bytes(), err
        print(f"      tentativa {attempt + 1}: {got!r} (WER {err:.2f})")
        if err <= 0.0:
            break
    if best_err > WER_OK and attempts == ATTEMPTS:
        print("      ainda ruim; insistindo mais um pouco")
        return await best_take(phrase, stt, attempts=ATTEMPTS * 2)
    if best is None:
        return None
    out = tts.cached_path(phrase)
    out.write_bytes(best)          # deixa a melhor no cache
    print(f"      melhor WER {best_err:.2f}" + ("" if best_err <= WER_OK else "  <-- ATENÇÃO"))
    return out


async def main():
    force = "--force" in sys.argv
    verify = "--verify" in sys.argv
    stt = None
    if verify:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from jarvis.stt.nemotron import NemotronStt
        stt = NemotronStt()
        stt._load_sync()

    lib_dir = ROOT / config.settings["tts"]["library_dir"]
    total = 0
    # a mesma frase aparece em intents diferentes (ex.: "Pronto.") e o cache é por
    # hash da frase — reusa a tomada já aprovada em vez de gerar (e sobrescrever) de novo
    approved: dict[str, Path] = {}
    for intent, phrases in config.responses.items():
        folder = lib_dir / intent
        folder.mkdir(parents=True, exist_ok=True)
        for i, phrase in enumerate(phrases):
            existing = list(folder.glob(f"{i:02d}_{intent}.*"))
            if existing and not force:
                continue
            print(f"[{intent}] {phrase}")
            if phrase in approved:
                path = approved[phrase]
                print("      (reusando a tomada já aprovada)")
            elif verify:
                path = await best_take(phrase, stt)
                if path:
                    approved[phrase] = path
            else:
                path = await tts.get_or_synthesize(phrase)
            if path:
                for old in existing:
                    old.unlink()
                out = folder / f"{i:02d}_{intent}{path.suffix}"
                out.write_bytes(path.read_bytes())
                total += 1
            else:
                print(f"   [FALHOU] {phrase}")
    print(f"\nBiblioteca pronta ({total} arquivos gerados).")


if __name__ == "__main__":
    asyncio.run(main())
