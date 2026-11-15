"""Cache SQLite de amostras por fonte/bairro/tipo com TTL (padrão 7 dias)."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


class SampleCache:
    def __init__(self, path: str, ttl_days: int = 7):
        self.path = path
        self.ttl = ttl_days * 86400
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS amostras (chave TEXT PRIMARY KEY, criado REAL NOT NULL, payload TEXT NOT NULL)"
            )

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    @staticmethod
    def chave(fonte: str, bairro: str, tipo: str) -> str:
        return f"{fonte}|{bairro}|{tipo}".lower()

    def get(self, chave: str) -> list[dict] | None:
        with self._conn() as c:
            row = c.execute("SELECT criado, payload FROM amostras WHERE chave = ?", (chave,)).fetchone()
        if not row or time.time() - row[0] > self.ttl:
            return None
        return json.loads(row[1])

    def set(self, chave: str, amostras: list[dict]) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO amostras (chave, criado, payload) VALUES (?, ?, ?)",
                (chave, time.time(), json.dumps(amostras, ensure_ascii=False)),
            )

    def purge_expired(self) -> int:
        with self._conn() as c:
            cur = c.execute("DELETE FROM amostras WHERE criado < ?", (time.time() - self.ttl,))
            return cur.rowcount
