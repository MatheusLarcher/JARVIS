"""Cliente Home Assistant local (REST) + modo mock pra desenvolver sem o HA real."""
import logging
import os

import httpx

from ..config import config

log = logging.getLogger("jarvis.ha")


class HomeAssistant:
    def __init__(self):
        cfg = config.settings["home_assistant"]
        self.mode = cfg.get("mode", "mock")
        self.url = cfg.get("url", "").rstrip("/")
        self.token = os.environ.get(cfg.get("token_env", "HA_TOKEN"), "")
        self._mock_states: dict[str, str] = {}
        self._client: httpx.AsyncClient | None = None

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def start(self):
        if self.mode == "real":
            self._client = httpx.AsyncClient(base_url=self.url, headers=self._headers(), timeout=5.0)

    async def stop(self):
        if self._client:
            await self._client.aclose()

    async def call_service(self, domain: str, service: str, entity_id: str) -> bool:
        if self.mode == "mock":
            state = "on" if service.endswith("turn_on") else "off"
            self._mock_states[entity_id] = state
            log.info("[MOCK HA] %s.%s -> %s = %s", domain, service, entity_id, state)
            return True
        r = await self._client.post(f"/api/services/{domain}/{service}",
                                    json={"entity_id": entity_id})
        return r.status_code < 300

    async def get_state(self, entity_id: str) -> dict | None:
        if self.mode == "mock":
            if entity_id.startswith("sensor.temperatura"):
                return {"state": "24.5", "attributes": {"unit_of_measurement": "°C"}}
            return {"state": self._mock_states.get(entity_id, "off"), "attributes": {}}
        r = await self._client.get(f"/api/states/{entity_id}")
        return r.json() if r.status_code == 200 else None

    async def temperature(self) -> float | None:
        ent = config.settings["home_assistant"].get("temperature_entity")
        if not ent:
            return None
        st = await self.get_state(ent)
        try:
            return float(st["state"]) if st else None
        except (ValueError, TypeError, KeyError):
            return None


ha = HomeAssistant()


def resolve_light_entity(room: str) -> str | None:
    """house/<cômodo>/luz_principal → entity_id."""
    room_devices = (config.house.get("house") or {}).get(room) or {}
    light = room_devices.get("luz_principal")
    return light.get("entity_id") if light else None
