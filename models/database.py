"""
資料庫模組 — 使用 SQLite 儲存每日記錄與問卷回覆
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from config import DATABASE_PATH


@dataclass
class EntryRecord:
    """單筆記錄（文字或語音轉文字後的內容）"""
    id: Optional[int]
    user_id: int
    content: str
    entry_type: str  # "text" 或 "voice"
    timestamp: str   # ISO 格式台灣時間
    diary_date: str  # 歸屬日期 YYYY-MM-DD


@dataclass
class SurveyRecord:
    """每日結算問卷"""
    id: Optional[int]
    user_id: int
    diary_date: str
    most_important: Optional[str]     # 最重要的事
    gratitude_1: Optional[str]        # 感恩第 1 件
    gratitude_2: Optional[str]        # 感恩第 2 件
    gratitude_3: Optional[str]        # 感恩第 3 件
    mood_score: Optional[int]         # 心情評分 -2 ~ +2
    additional_notes: Optional[str]   # 補充內容
    completed: bool = False           # 問卷是否完成
    created_at: Optional[str] = None


class Database:
    """SQLite 資料庫操作封裝"""

    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        """建立資料表"""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS entries (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    content     TEXT    NOT NULL,
                    entry_type  TEXT    NOT NULL DEFAULT 'text',
                    timestamp   TEXT    NOT NULL,
                    diary_date  TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS surveys (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id         INTEGER NOT NULL,
                    diary_date      TEXT    NOT NULL,
                    most_important  TEXT,
                    gratitude_1     TEXT,
                    gratitude_2     TEXT,
                    gratitude_3     TEXT,
                    mood_score      INTEGER,
                    additional_notes TEXT,
                    completed       INTEGER NOT NULL DEFAULT 0,
                    created_at      TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS generated_diaries (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    diary_date  TEXT    NOT NULL UNIQUE,
                    content     TEXT    NOT NULL,
                    uploaded    INTEGER NOT NULL DEFAULT 0,
                    created_at  TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key         TEXT PRIMARY KEY,
                    value       TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_entries_user_date
                    ON entries(user_id, diary_date);
                CREATE INDEX IF NOT EXISTS idx_surveys_user_date
                    ON surveys(user_id, diary_date);
            """)

    # ── 記錄操作 ────────────────────────────────

    def add_entry(self, user_id: int, content: str, entry_type: str,
                  timestamp: str, diary_date: str) -> int:
        """新增一筆生活記錄"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "INSERT INTO entries (user_id, content, entry_type, timestamp, diary_date) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, content, entry_type, timestamp, diary_date),
            )
            return cursor.lastrowid

    def get_entries_by_date(self, user_id: int, diary_date: str) -> list[EntryRecord]:
        """取得指定日期的所有記錄"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM entries WHERE user_id = ? AND diary_date = ? ORDER BY timestamp",
                (user_id, diary_date),
            ).fetchall()
            return [
                EntryRecord(
                    id=r["id"], user_id=r["user_id"], content=r["content"],
                    entry_type=r["entry_type"], timestamp=r["timestamp"],
                    diary_date=r["diary_date"],
                )
                for r in rows
            ]

    def get_entry_count_by_date(self, user_id: int, diary_date: str) -> int:
        """取得指定日期的記錄數量"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM entries WHERE user_id = ? AND diary_date = ?",
                (user_id, diary_date),
            ).fetchone()
            return row["cnt"]

    # ── 問卷操作 ────────────────────────────────

    def create_survey(self, user_id: int, diary_date: str, created_at: str) -> int:
        """建立當天的問卷"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "INSERT INTO surveys (user_id, diary_date, created_at) VALUES (?, ?, ?)",
                (user_id, diary_date, created_at),
            )
            return cursor.lastrowid

    def get_survey(self, user_id: int, diary_date: str) -> Optional[SurveyRecord]:
        """取得指定日期的問卷"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM surveys WHERE user_id = ? AND diary_date = ? "
                "ORDER BY id DESC LIMIT 1",
                (user_id, diary_date),
            ).fetchone()
            if not row:
                return None
            return SurveyRecord(
                id=row["id"], user_id=row["user_id"], diary_date=row["diary_date"],
                most_important=row["most_important"],
                gratitude_1=row["gratitude_1"], gratitude_2=row["gratitude_2"],
                gratitude_3=row["gratitude_3"], mood_score=row["mood_score"],
                additional_notes=row["additional_notes"],
                completed=bool(row["completed"]), created_at=row["created_at"],
            )

    def update_survey_field(self, survey_id: int, field: str, value) -> None:
        """更新問卷的單一欄位"""
        allowed = {
            "most_important", "gratitude_1", "gratitude_2", "gratitude_3",
            "mood_score", "additional_notes", "completed",
        }
        if field not in allowed:
            raise ValueError(f"不允許更新欄位: {field}")
        with self._get_conn() as conn:
            conn.execute(
                f"UPDATE surveys SET {field} = ? WHERE id = ?",
                (value, survey_id),
            )

    # ── 日記操作 ────────────────────────────────

    def save_diary(self, user_id: int, diary_date: str, content: str,
                   created_at: str, uploaded: bool = False) -> int:
        """儲存生成的日記"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "INSERT OR REPLACE INTO generated_diaries "
                "(user_id, diary_date, content, uploaded, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, diary_date, content, int(uploaded), created_at),
            )
            return cursor.lastrowid

    def get_diary(self, user_id: int, diary_date: str) -> Optional[dict]:
        """取得指定日期的日記"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM generated_diaries WHERE user_id = ? AND diary_date = ?",
                (user_id, diary_date),
            ).fetchone()
            return dict(row) if row else None

    def mark_diary_uploaded(self, user_id: int, diary_date: str) -> None:
        """標記日記已上傳至 Google Drive"""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE generated_diaries SET uploaded = 1 "
                "WHERE user_id = ? AND diary_date = ?",
                (user_id, diary_date),
            )

    # ── 統計 ────────────────────────────────────

    def get_all_user_ids(self) -> list[int]:
        """取得所有曾使用過的 user_id"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT user_id FROM entries"
            ).fetchall()
            return [r["user_id"] for r in rows]

    def get_mood_scores(self, user_id: int, limit: int = 7) -> list[dict]:
        """取得最近 N 天的心情評分"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT diary_date, mood_score FROM surveys "
                "WHERE user_id = ? AND mood_score IS NOT NULL "
                "ORDER BY diary_date DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    # ── 設定操作 ────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        """取得設定值"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        """儲存設定值"""
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
