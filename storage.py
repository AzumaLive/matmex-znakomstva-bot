import json
import os
import sqlite3

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

import db


class SQLiteStorage(BaseStorage):
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or db.DB_PATH
        d = os.path.dirname(os.path.abspath(self.db_path))
        if d:
            os.makedirs(d, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fsm_storage ("
            "key TEXT PRIMARY KEY, "
            "state TEXT, "
            "data TEXT)"
        )
        conn.commit()
        conn.close()

    @staticmethod
    def _key(key: StorageKey) -> str:
        return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{key.destiny}"

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        state_str = state.state if isinstance(state, State) else (str(state) if state else None)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO fsm_storage(key, state, data) VALUES (?, ?, '{}') "
            "ON CONFLICT(key) DO UPDATE SET state = excluded.state",
            (self._key(key), state_str),
        )
        conn.commit()
        conn.close()

    async def get_state(self, key: StorageKey) -> str | None:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT state FROM fsm_storage WHERE key = ?", (self._key(key),)
        ).fetchone()
        conn.close()
        return row[0] if row else None

    async def set_data(self, key: StorageKey, data) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO fsm_storage(key, state, data) VALUES (?, NULL, ?) "
            "ON CONFLICT(key) DO UPDATE SET data = excluded.data",
            (self._key(key), json.dumps(dict(data), ensure_ascii=False)),
        )
        conn.commit()
        conn.close()

    async def get_data(self, key: StorageKey) -> dict:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT data FROM fsm_storage WHERE key = ?", (self._key(key),)
        ).fetchone()
        conn.close()
        if not row or not row[0]:
            return {}
        return json.loads(row[0])

    async def close(self) -> None:
        pass
