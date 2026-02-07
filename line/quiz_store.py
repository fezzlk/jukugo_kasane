import os
import sqlite3
from datetime import datetime


class SqliteQuizStore:
    def __init__(self, db_path: str, logger):
        self.db_path = db_path
        self.logger = logger
        self._ensure_db()

    def _ensure_db(self) -> None:
        parent_dir = os.path.dirname(self.db_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS quiz_items (
                    user_id TEXT NOT NULL,
                    number INTEGER NOT NULL,
                    word TEXT NOT NULL,
                    quiz_mode TEXT NOT NULL DEFAULT 'intersection',
                    quiz_prompt TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, number)
                )
                """
            )
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(quiz_items)").fetchall()
            }
            if "quiz_mode" not in columns:
                conn.execute(
                    "ALTER TABLE quiz_items ADD COLUMN quiz_mode TEXT NOT NULL DEFAULT 'intersection'"
                )
            if "quiz_prompt" not in columns:
                conn.execute(
                    "ALTER TABLE quiz_items ADD COLUMN quiz_prompt TEXT NOT NULL DEFAULT ''"
                )

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def set_word(
        self,
        user_id: str,
        number: int,
        word: str,
        quiz_mode: str = "intersection",
        quiz_prompt: str = "",
    ) -> str:
        old_word = self.get_word(user_id, number)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO quiz_items (user_id, number, word, quiz_mode, quiz_prompt, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, number)
                DO UPDATE SET word=excluded.word, quiz_mode=excluded.quiz_mode,
                quiz_prompt=excluded.quiz_prompt,
                updated_at=excluded.updated_at
                """,
                (user_id, number, word, quiz_mode, quiz_prompt, self._now()),
            )
        return old_word or ""

    def get_word(self, user_id: str, number: int) -> str:
        item = self.get_quiz_item(user_id, number)
        return item["word"] if item else ""

    def get_quiz_item(self, user_id: str, number: int) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT word, quiz_mode, quiz_prompt FROM quiz_items WHERE user_id=? AND number=?",
                (user_id, number),
            ).fetchone()
        if not row:
            return {}
        return {
            "word": row["word"],
            "quiz_mode": row["quiz_mode"] or "intersection",
            "quiz_prompt": row["quiz_prompt"] or "",
        }

    def delete_word(self, user_id: str, number: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM quiz_items WHERE user_id=? AND number=?",
                (user_id, number),
            )

    def list_words(self, user_id: str) -> dict:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT number, word FROM quiz_items WHERE user_id=?",
                (user_id,),
            ).fetchall()
        result = {}
        for row in rows:
            result[int(row["number"])] = row["word"]
        return result

    def list_quiz_items(self, user_id: str) -> dict:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT number, word, quiz_mode, quiz_prompt FROM quiz_items WHERE user_id=?",
                (user_id,),
            ).fetchall()
        result = {}
        for row in rows:
            result[int(row["number"])] = {
                "word": row["word"],
                "quiz_mode": row["quiz_mode"] or "intersection",
                "quiz_prompt": row["quiz_prompt"] or "",
            }
        return result

    def _now(self) -> str:
        return datetime.utcnow().isoformat() + "Z"


class DatastoreQuizStore:
    def __init__(self, project_id: str, logger, kind: str = "line_quiz_items"):
        self.project_id = project_id
        self.logger = logger
        self.kind = kind
        self._client = None

    def _client_or_create(self):
        if self._client is None:
            from google.cloud import datastore

            if self.project_id:
                self._client = datastore.Client(project=self.project_id)
            else:
                self._client = datastore.Client()
        return self._client

    def _key(self, user_id: str, number: int):
        key_name = f"{user_id}:{number}"
        return self._client_or_create().key(self.kind, key_name)

    def set_word(
        self,
        user_id: str,
        number: int,
        word: str,
        quiz_mode: str = "intersection",
        quiz_prompt: str = "",
    ) -> str:
        old_word = self.get_word(user_id, number)
        from google.cloud import datastore

        entity = datastore.Entity(key=self._key(user_id, number))
        entity.update(
            {
                "user_id": user_id,
                "number": number,
                "word": word,
                "quiz_mode": quiz_mode,
                "quiz_prompt": quiz_prompt,
                "updated_at": datetime.utcnow(),
            }
        )
        self._client_or_create().put(entity)
        return old_word or ""

    def get_word(self, user_id: str, number: int) -> str:
        item = self.get_quiz_item(user_id, number)
        return item["word"] if item else ""

    def get_quiz_item(self, user_id: str, number: int) -> dict:
        entity = self._client_or_create().get(self._key(user_id, number))
        if not entity:
            return {}
        return {
            "word": entity.get("word", "") or "",
            "quiz_mode": entity.get("quiz_mode", "intersection") or "intersection",
            "quiz_prompt": entity.get("quiz_prompt", "") or "",
        }

    def delete_word(self, user_id: str, number: int) -> None:
        self._client_or_create().delete(self._key(user_id, number))

    def list_words(self, user_id: str) -> dict:
        query = self._client_or_create().query(kind=self.kind)
        query.add_filter("user_id", "=", user_id)
        result = {}
        for entity in query.fetch():
            try:
                number = int(entity.get("number", 0))
            except (TypeError, ValueError):
                continue
            word = entity.get("word", "")
            if word:
                result[number] = word
        return result

    def list_quiz_items(self, user_id: str) -> dict:
        query = self._client_or_create().query(kind=self.kind)
        query.add_filter("user_id", "=", user_id)
        result = {}
        for entity in query.fetch():
            try:
                number = int(entity.get("number", 0))
            except (TypeError, ValueError):
                continue
            word = entity.get("word", "")
            if not word:
                continue
            result[number] = {
                "word": word,
                "quiz_mode": entity.get("quiz_mode", "intersection") or "intersection",
                "quiz_prompt": entity.get("quiz_prompt", "") or "",
            }
        return result
