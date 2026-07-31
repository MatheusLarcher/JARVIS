"""Context Engine: consolida quem pediu, de onde e em que situação.

Fontes combinadas (nenhuma obrigatória): device_id/config, rede Wi-Fi reportada
pelo device, GPS/geofence (futuro), Bluetooth (futuro), contexto anterior.
"""
import time
import uuid
from dataclasses import dataclass, field

from ..config import config


@dataclass
class DeviceContext:
    device_id: str
    device_type: str
    user_id: str = "matheus"
    source: str = "microphone"
    place: str | None = None      # home | empresa | carro | rua
    room: str | None = None
    network: str | None = None
    connection: str = "local"
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    extra: dict = field(default_factory=dict)

    def snapshot(self) -> dict:
        return {
            "device_id": self.device_id, "device_type": self.device_type,
            "user_id": self.user_id, "source": self.source, "place": self.place,
            "room": self.room, "network": self.network, "connection": self.connection,
            "timestamp": time.time(), "session_id": self.session_id, **self.extra,
        }


class ContextEngine:
    def __init__(self):
        self._contexts: dict[str, DeviceContext] = {}

    def register(self, device_id: str, hello: dict) -> DeviceContext:
        dev_cfg = config.devices.get(device_id, {})
        ctx = DeviceContext(
            device_id=device_id,
            device_type=dev_cfg.get("type", hello.get("device_type", "unknown")),
            room=hello.get("room") or dev_cfg.get("default_room"),
            network=hello.get("network"),
        )
        ctx.place = self._infer_place(ctx)
        self._contexts[device_id] = ctx
        return ctx

    def update(self, device_id: str, patch: dict) -> DeviceContext | None:
        ctx = self._contexts.get(device_id)
        if not ctx:
            return None
        for key in ("room", "network", "place", "connection", "source"):
            if key in patch and patch[key] is not None:
                setattr(ctx, key, patch[key])
        for k, v in patch.items():
            if k in ("gps", "bluetooth", "battery", "moving"):
                ctx.extra[k] = v
        if "network" in patch:
            ctx.place = self._infer_place(ctx)
        return ctx

    def get(self, device_id: str) -> DeviceContext | None:
        return self._contexts.get(device_id)

    def new_session(self, device_id: str):
        ctx = self._contexts.get(device_id)
        if ctx:
            ctx.session_id = uuid.uuid4().hex[:12]
        return ctx

    def _infer_place(self, ctx: DeviceContext) -> str | None:
        # rede Wi-Fi conhecida > tipo do device > desconhecido
        if ctx.network:
            for place, info in config.house.get("places", {}).items():
                if ctx.network in (info.get("networks") or []):
                    return place
        if ctx.device_type in ("tablet", "pc", "web"):
            return "home"
        return None

    def resolve_room(self, ctx: DeviceContext, slot_room: str | None) -> str | None:
        """Cômodo do comando: slot explícito > cômodo do contexto > None (ambíguo)."""
        if slot_room:
            return slot_room
        if ctx and ctx.room:
            return ctx.room
        return None


context_engine = ContextEngine()
