"""TTS desacoplado: perfis de voz em config/settings.yml, cache por hash(frase+perfil).

Motores:
  clone → serviço local de voz clonada (server/voice_service, porta 8041)
  edge  → edge-tts (rápido, usado como fallback quando o clone está fora)

Trocar de motor = implementar TtsEngine e registrar em _ENGINES.
"""
import hashlib
import logging
from pathlib import Path

import httpx

from ..config import ROOT, config

log = logging.getLogger("jarvis.tts")


class TtsEngine:
    async def synthesize(self, text: str, profile: dict, out_path: Path) -> bool:
        raise NotImplementedError


class EdgeTts(TtsEngine):
    async def synthesize(self, text: str, profile: dict, out_path: Path) -> bool:
        import edge_tts
        com = edge_tts.Communicate(text, profile.get("voice", "pt-BR-AntonioNeural"),
                                   rate=profile.get("rate", "+0%"),
                                   pitch=profile.get("pitch", "+0Hz"))
        await com.save(str(out_path))
        return out_path.exists() and out_path.stat().st_size > 0


class CloneTts(TtsEngine):
    """Voz clonada do JARVIS, servida pelo processo do env jarvis-tts."""

    async def synthesize(self, text: str, profile: dict, out_path: Path) -> bool:
        url = profile.get("service_url", "http://127.0.0.1:8041")
        payload = {
            "text": text,
            "language": profile.get("language", "pt"),
            "exaggeration": profile.get("exaggeration", 0.5),
            "cfg_weight": profile.get("cfg_weight", 0.5),
            "temperature": profile.get("temperature", 0.7),
        }
        async with httpx.AsyncClient(timeout=profile.get("timeout_s", 120)) as client:
            r = await client.post(f"{url}/tts", json=payload)
        if r.status_code != 200:
            log.warning("serviço de voz respondeu %s", r.status_code)
            return False
        out_path.write_bytes(r.content)
        return out_path.stat().st_size > 0


_ENGINES: dict[str, TtsEngine] = {"edge": EdgeTts(), "clone": CloneTts()}


class TtsService:
    def __init__(self):
        cfg = config.settings["tts"]
        self.cache_dir = ROOT / cfg["cache_dir"]
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_profile = cfg["default_profile"]
        self.profiles = cfg["voice_profiles"]

    def _key(self, text: str, profile_name: str) -> str:
        return hashlib.sha1(f"{profile_name}|{text}".encode()).hexdigest()[:20]

    def _ext(self, profile: dict) -> str:
        return ".wav" if profile.get("engine") == "clone" else ".mp3"

    def cached_path(self, text: str, profile_name: str | None = None) -> Path:
        name = profile_name or self.default_profile
        profile = self.profiles[name]
        return self.cache_dir / f"{self._key(text, name)}{self._ext(profile)}"

    def is_cached(self, text: str, profile_name: str | None = None) -> bool:
        return self.cached_path(text, profile_name).exists()

    async def synthesize_fresh(self, text: str, profile_name: str | None = None,
                               **overrides) -> Path | None:
        """Gera ignorando o cache (e sobrescreve). Usado pra regerar frase ruim."""
        name = profile_name or self.default_profile
        path = self.cached_path(text, name)
        profile = {**self.profiles[name], **overrides}
        try:
            ok = await _ENGINES[profile["engine"]].synthesize(text, profile, path)
            return path if ok else None
        except Exception as e:
            log.warning("TTS falhou (%s): %s", e.__class__.__name__, text[:40])
            return None

    async def get_or_synthesize(self, text: str, profile_name: str | None = None) -> Path | None:
        """Devolve o arquivo de áudio da frase, reutilizando cache quando existir."""
        name = profile_name or self.default_profile
        path = self.cached_path(text, name)
        if path.exists():
            return path
        profile = self.profiles[name]
        engine_name = profile["engine"]
        try:
            ok = await _ENGINES[engine_name].synthesize(text, profile, path)
            if ok:
                return path
        except Exception as e:
            log.warning("TTS %s falhou (%s): %s", engine_name, e.__class__.__name__, text[:40])

        # nunca ficar mudo: cai pro motor de reserva do perfil
        fb = profile.get("fallback")
        if fb and fb in self.profiles:
            log.info("usando voz de reserva (%s) para: %s", fb, text[:40])
            return await self.get_or_synthesize(text, fb)
        return None


tts = TtsService()
