"""TTS desacoplado: perfis de voz em config/settings.yml, cache por hash(frase+perfil).

Trocar de motor = implementar TtsEngine e registrar em _ENGINES.
"""
import hashlib
import logging
from pathlib import Path

from ..config import ROOT, config

log = logging.getLogger("jarvis.tts")


class TtsEngine:
    async def synthesize(self, text: str, profile: dict, out_path: Path) -> bool:
        raise NotImplementedError


class EdgeTts(TtsEngine):
    async def synthesize(self, text: str, profile: dict, out_path: Path) -> bool:
        import edge_tts
        com = edge_tts.Communicate(text, profile["voice"],
                                   rate=profile.get("rate", "+0%"),
                                   pitch=profile.get("pitch", "+0Hz"))
        await com.save(str(out_path))
        return out_path.exists() and out_path.stat().st_size > 0


_ENGINES: dict[str, TtsEngine] = {"edge": EdgeTts()}


class TtsService:
    def __init__(self):
        cfg = config.settings["tts"]
        self.cache_dir = ROOT / cfg["cache_dir"]
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_profile = cfg["default_profile"]
        self.profiles = cfg["voice_profiles"]

    def _key(self, text: str, profile_name: str) -> str:
        return hashlib.sha1(f"{profile_name}|{text}".encode()).hexdigest()[:20]

    def cached_path(self, text: str, profile_name: str | None = None) -> Path:
        name = profile_name or self.default_profile
        return self.cache_dir / f"{self._key(text, name)}.mp3"

    async def get_or_synthesize(self, text: str, profile_name: str | None = None) -> Path | None:
        """Devolve o arquivo de áudio da frase, reutilizando cache quando existir."""
        name = profile_name or self.default_profile
        path = self.cached_path(text, name)
        if path.exists():
            return path
        profile = self.profiles[name]
        engine = _ENGINES[profile["engine"]]
        try:
            ok = await engine.synthesize(text, profile, path)
            return path if ok else None
        except Exception:
            log.exception("TTS falhou pra: %s", text)
            return None


tts = TtsService()
