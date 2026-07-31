import json
import time
from pathlib import Path

import aiosqlite

from ..config import DATA_DIR

DB_PATH = DATA_DIR / "jarvis.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    device_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    transcript TEXT,
    intent TEXT,
    handler TEXT,            -- local | agent
    response_text TEXT,
    metrics_json TEXT
);
CREATE TABLE IF NOT EXISTS memory_kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS device_state (
    device_id TEXT PRIMARY KEY,
    last_seen_ts REAL,
    context_json TEXT
);
"""


class Store:
    def __init__(self):
        self._db: aiosqlite.Connection | None = None

    async def open(self):
        Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(DB_PATH)
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()

    async def log_interaction(self, device_id, session_id, transcript, intent,
                              handler, response_text, metrics: dict):
        await self._db.execute(
            "INSERT INTO interactions (ts, device_id, session_id, transcript, intent, handler, response_text, metrics_json)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (time.time(), device_id, session_id, transcript, intent, handler,
             response_text, json.dumps(metrics, ensure_ascii=False)))
        await self._db.commit()

    async def recent_history(self, device_id: str, limit: int = 6) -> list[dict]:
        """Memória curta: últimas trocas do dispositivo pro contexto do agente."""
        cur = await self._db.execute(
            "SELECT transcript, response_text FROM interactions WHERE device_id=? "
            "AND transcript IS NOT NULL ORDER BY id DESC LIMIT ?", (device_id, limit))
        rows = await cur.fetchall()
        return [{"user": r[0], "jarvis": r[1]} for r in reversed(rows)]

    async def save_device_context(self, device_id: str, context: dict):
        await self._db.execute(
            "INSERT INTO device_state (device_id, last_seen_ts, context_json) VALUES (?,?,?) "
            "ON CONFLICT(device_id) DO UPDATE SET last_seen_ts=excluded.last_seen_ts, context_json=excluded.context_json",
            (device_id, time.time(), json.dumps(context, ensure_ascii=False)))
        await self._db.commit()


store = Store()
