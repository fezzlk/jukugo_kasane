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
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, number)
                )
                """
            )

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def set_word(self, user_id: str, number: int, word: str) -> str:
        old_word = self.get_word(user_id, number)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO quiz_items (user_id, number, word, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, number)
                DO UPDATE SET word=excluded.word, updated_at=excluded.updated_at
                """,
                (user_id, number, word, self._now()),
            )
        return old_word or ""

    def get_word(self, user_id: str, number: int) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT word FROM quiz_items WHERE user_id=? AND number=?",
                (user_id, number),
            ).fetchone()
        return row["word"] if row else ""

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

    def _now(self) -> str:
        return datetime.utcnow().isoformat() + "Z"


class FirestoreQuizStore:
    def __init__(self, project_id: str, logger, collection: str = "line_quiz_users"):
        self.project_id = project_id
        self.logger = logger
        self.collection = collection
        self._client = None

    def _client_or_create(self):
        if self._client is None:
            from google.cloud import firestore

            if self.project_id:
                self._client = firestore.Client(project=self.project_id)
            else:
                self._client = firestore.Client()
        return self._client

    def set_word(self, user_id: str, number: int, word: str) -> str:
        old_word = self.get_word(user_id, number)
        doc_ref = (
            self._client_or_create()
            .collection(self.collection)
            .document(user_id)
            .collection("items")
            .document(str(number))
        )
        doc_ref.set(
            {"word": word, "updated_at": datetime.utcnow()},
        )
        return old_word or ""

    def get_word(self, user_id: str, number: int) -> str:
        doc_ref = (
            self._client_or_create()
            .collection(self.collection)
            .document(user_id)
            .collection("items")
            .document(str(number))
        )
        doc = doc_ref.get()
        if not doc.exists:
            return ""
        data = doc.to_dict() or {}
        return data.get("word", "")

    def delete_word(self, user_id: str, number: int) -> None:
        doc_ref = (
            self._client_or_create()
            .collection(self.collection)
            .document(user_id)
            .collection("items")
            .document(str(number))
        )
        doc_ref.delete()

    def list_words(self, user_id: str) -> dict:
        col_ref = (
            self._client_or_create()
            .collection(self.collection)
            .document(user_id)
            .collection("items")
        )
        result = {}
        for doc in col_ref.stream():
            try:
                number = int(doc.id)
            except ValueError:
                continue
            data = doc.to_dict() or {}
            word = data.get("word", "")
            if word:
                result[number] = word
        return result
