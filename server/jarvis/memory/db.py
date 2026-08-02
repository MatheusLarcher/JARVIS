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
-- o que virou material de aprendizado: áudio da fala, rota escolhida e o que deu
CREATE TABLE IF NOT EXISTS registros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    device_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    transcricao TEXT,
    audio_path TEXT,
    agente TEXT,
    rota_json TEXT,          -- decisão do roteador (escolha, confiança, motivo)
    resposta TEXT,
    erro TEXT,
    metricas_json TEXT,
    -- preenchidos depois, pelo observador ou por correção sua
    revisado INTEGER DEFAULT 0,
    transcricao_correta TEXT,
    agente_correto TEXT,
    observacao TEXT
);
CREATE INDEX IF NOT EXISTS idx_registros_ts ON registros(ts);
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

    async def salvar_registro(self, r) -> int | None:
        """Grava a interação completa (com áudio e decisão) pra aprender depois."""
        try:
            cur = await self._db.execute(
                "INSERT INTO registros (ts, device_id, session_id, transcricao, "
                "audio_path, agente, rota_json, resposta, erro, metricas_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (time.time(), r.device_id, r.session_id, r.transcricao, r.audio_path,
                 r.agente, json.dumps(r.rota, ensure_ascii=False), r.resposta, r.erro,
                 json.dumps(r.metricas, ensure_ascii=False)))
            await self._db.commit()
            return cur.lastrowid
        except Exception:
            return None

    async def limpar_registros(self, antes_de: float) -> int:
        """Apaga linhas cujo áudio já foi removido — a tabela não pode crescer
        pra sempre num servidor que fica ligado o dia todo, e registro sem WAV
        não serve nem pra ouvir nem pra treinar."""
        cur = await self._db.execute("DELETE FROM registros WHERE ts < ?",
                                     (antes_de,))
        await self._db.commit()
        return cur.rowcount or 0

    async def registros_para_revisar(self, limit: int = 20) -> list[dict]:
        cur = await self._db.execute(
            "SELECT id, ts, transcricao, audio_path, agente, rota_json, resposta, erro "
            "FROM registros WHERE revisado = 0 ORDER BY id DESC LIMIT ?", (limit,))
        cols = ["id", "ts", "transcricao", "audio_path", "agente", "rota_json",
                "resposta", "erro"]
        return [dict(zip(cols, row)) for row in await cur.fetchall()]

    async def anotar_registro(self, registro_id: int, observacao: str,
                              agente_correto: str | None = None,
                              transcricao_correta: str | None = None):
        await self._db.execute(
            "UPDATE registros SET observacao=?, agente_correto=?, "
            "transcricao_correta=?, revisado=1 WHERE id=?",
            (observacao, agente_correto, transcricao_correta, registro_id))
        await self._db.commit()

    async def pedido_repetido(self, device_id: str, transcricao: str,
                              janela_s: float = 120,
                              ignorar_id: int | None = None) -> bool:
        """Você pediu a mesma coisa de novo agora há pouco? Sinal de que falhou.

        `ignorar_id` é obrigatório na prática: a checagem roda depois de gravar,
        então sem isso a interação se compara com ela mesma e TUDO vira
        "repetido" (foi o que aconteceu no primeiro teste de verdade).
        """
        if not transcricao:
            return False
        cur = await self._db.execute(
            "SELECT transcricao FROM registros WHERE device_id=? AND ts > ? "
            "AND id != ? ORDER BY id DESC LIMIT 3",
            (device_id, time.time() - janela_s, ignorar_id or -1))
        anteriores = [r[0] or "" for r in await cur.fetchall()]
        alvo = transcricao.lower().strip()
        return any(a.lower().strip() == alvo for a in anteriores)

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
