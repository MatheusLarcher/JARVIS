"""Gera os áudios da biblioteca de respostas (config/responses.yml) com o TTS configurado.

Uso: python server/scripts/build_library.py
Idempotente: só gera o que não existe.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis.config import ROOT, config  # noqa: E402
from jarvis.tts.engine import tts  # noqa: E402


async def main():
    lib_dir = ROOT / config.settings["tts"]["library_dir"]
    total = 0
    for intent, phrases in config.responses.items():
        folder = lib_dir / intent
        folder.mkdir(parents=True, exist_ok=True)
        for i, phrase in enumerate(phrases):
            out = folder / f"{i:02d}_{intent}.mp3"
            if out.exists():
                continue
            path = await tts.get_or_synthesize(phrase)
            if path:
                out.write_bytes(path.read_bytes())
                total += 1
                print(f"[ok] {intent}: {phrase} -> {out.name}")
            else:
                print(f"[FALHOU] {intent}: {phrase}")
    print(f"Biblioteca pronta ({total} novos arquivos).")


if __name__ == "__main__":
    asyncio.run(main())
