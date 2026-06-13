"""
SQLite database moduli
Foydalanuvchilar, to'lovlar, generatsiyalar
"""

import sqlite3
import json
import os
from datetime import datetime, date
from typing import Optional

DB_PATH = os.getenv("DB_PATH", "edubot.db")


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            balance INTEGER DEFAULT 0,
            free_used INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            doc_type TEXT,
            topic TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS pending_requests (
            user_id INTEGER PRIMARY KEY,
            data TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """)
        self.conn.commit()

    def add_user(self, user_id: int, first_name: str, username: str):
        self.conn.execute("""
            INSERT OR IGNORE INTO users (id, first_name, username)
            VALUES (?, ?, ?)
        """, (user_id, first_name, username or ""))
        self.conn.commit()

    def get_free_used(self, user_id: int) -> bool:
        row = self.conn.execute(
            "SELECT free_used FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return bool(row["free_used"]) if row else False

    def mark_free_used(self, user_id: int):
        self.conn.execute(
            "UPDATE users SET free_used = 1 WHERE id = ?", (user_id,)
        )
        self.conn.commit()

    def get_balance(self, user_id: int) -> int:
        row = self.conn.execute(
            "SELECT balance FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return row["balance"] if row else 0

    def add_balance(self, user_id: int, amount: int):
        self.conn.execute(
            "UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id)
        )
        self.conn.commit()

    def deduct_balance(self, user_id: int, amount: int):
        self.conn.execute(
            "UPDATE users SET balance = balance - ? WHERE id = ?", (amount, user_id)
        )
        self.conn.commit()

    def log_generation(self, user_id: int, doc_type: str, topic: str):
        self.conn.execute("""
            INSERT INTO generations (user_id, doc_type, topic)
            VALUES (?, ?, ?)
        """, (user_id, doc_type, topic))
        self.conn.commit()

    def get_total_generations(self, user_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM generations WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["cnt"] if row else 0

    def save_pending_request(self, user_id: int, data: dict):
        self.conn.execute("""
            INSERT OR REPLACE INTO pending_requests (user_id, data)
            VALUES (?, ?)
        """, (user_id, json.dumps(data)))
        self.conn.commit()

    def get_pending_request(self, user_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT data FROM pending_requests WHERE user_id = ?", (user_id,)
        ).fetchone()
        return json.loads(row["data"]) if row else None

    def clear_pending(self, user_id: int):
        self.conn.execute(
            "DELETE FROM pending_requests WHERE user_id = ?", (user_id,)
        )
        self.conn.commit()

    def get_stats(self) -> dict:
        users = self.conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
        docs = self.conn.execute("SELECT COUNT(*) as cnt FROM generations").fetchone()["cnt"]
        today_str = date.today().isoformat()
        today = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM generations WHERE created_at LIKE ?",
            (f"{today_str}%",)
        ).fetchone()["cnt"]

        # Taxminiy daromad: (jami - bepul foydalanuvchilar soni) * narx
        free_count = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM users WHERE free_used = 1"
        ).fetchone()["cnt"]
        paid_docs = max(0, docs - free_count)
        revenue = paid_docs * 8000

        return {
            "users": users,
            "docs": docs,
            "today": today,
            "revenue": revenue
        }
