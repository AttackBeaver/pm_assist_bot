import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import os
DB_PATH = Path(os.getenv("DATA_DIR", Path(__file__).parent)) / "tasks.db"

def init_db() -> None:
    db_dir = DB_PATH.parent
    db_dir.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'pending',
            deadline TEXT,
            deadline_timestamp INTEGER,
            responsible_telegram_id INTEGER,
            author_telegram_id INTEGER,
            yougile_card_id TEXT,
            chat_id INTEGER,
            created_at TEXT,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            is_away INTEGER DEFAULT 0,
            away_reason TEXT,
            away_until TEXT
        );
        CREATE TABLE IF NOT EXISTS user_stats (
            telegram_id INTEGER PRIMARY KEY,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            achievements TEXT DEFAULT '[]',
            tasks_completed INTEGER DEFAULT 0,
            tasks_created INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS task_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            status_from TEXT,
            status_to TEXT NOT NULL,
            changed_at TEXT NOT NULL,
            comment TEXT
        );
        ''')
        # Миграции
        try:
            conn.execute("ALTER TABLE tasks ADD COLUMN completed_at TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE tasks ADD COLUMN author_telegram_id INTEGER")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE user_stats ADD COLUMN tasks_completed INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE user_stats ADD COLUMN tasks_created INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_task_history_task_id ON task_history(task_id)")

@contextmanager
def _connect() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

init_db()

# --- Пользователи ---
def add_user(telegram_id: int, username: Optional[str] = None, full_name: Optional[str] = None) -> None:
    with _connect() as conn:
        conn.execute("INSERT OR IGNORE INTO users (telegram_id, username, full_name) VALUES (?, ?, ?)",
                     (telegram_id, username, full_name))

def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        return dict(row) if row else None

def set_user_away(telegram_id: int, reason: str, until: Optional[datetime] = None) -> None:
    until_str = until.isoformat() if until else None
    with _connect() as conn:
        conn.execute("UPDATE users SET is_away = 1, away_reason = ?, away_until = ? WHERE telegram_id = ?",
                     (reason, until_str, telegram_id))

def clear_user_away(telegram_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET is_away = 0, away_reason = NULL, away_until = NULL WHERE telegram_id = ?",
                     (telegram_id,))

def get_pending_user_ids() -> List[int]:
    with _connect() as conn:
        rows = conn.execute("SELECT DISTINCT responsible_telegram_id FROM tasks WHERE status = 'pending'").fetchall()
        return [row["responsible_telegram_id"] for row in rows]

# --- История задач ---
def add_task_history(task_id: str, status_to: str, status_from: str = None, comment: str = None) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO task_history (task_id, status_from, status_to, changed_at, comment) VALUES (?, ?, ?, ?, ?)",
            (task_id, status_from, status_to, datetime.now().isoformat(), comment)
        )

# --- Задачи ---
def add_task(
    task_id: str,
    title: str,
    description: str,
    responsible_telegram_id: int,
    author_telegram_id: int,
    deadline: Optional[str] = None,
    deadline_timestamp: Optional[int] = None,
    yougile_card_id: Optional[str] = None,
    chat_id: Optional[int] = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO tasks
                (id, title, description, status, deadline, deadline_timestamp,
                 responsible_telegram_id, author_telegram_id, yougile_card_id, chat_id, created_at)
               VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, title, description, deadline, deadline_timestamp,
             responsible_telegram_id, author_telegram_id, yougile_card_id, chat_id, datetime.now().isoformat())
        )
    update_user_stats(author_telegram_id, xp_delta=5, tasks_created_delta=1)
    tasks = get_tasks_by_user(author_telegram_id)
    if len(tasks) == 1:
        update_user_stats(author_telegram_id, achievements_to_add=["Первая задача"])
    add_task_history(task_id, 'pending', comment='Задача создана')

def get_tasks_by_user(telegram_id: int, status: Optional[str] = None) -> List[Dict[str, Any]]:
    with _connect() as conn:
        if status:
            rows = conn.execute(
                """SELECT id, title, description, status, deadline, yougile_card_id
                   FROM tasks WHERE responsible_telegram_id = ? AND status = ?
                   ORDER BY deadline_timestamp ASC""",
                (telegram_id, status)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, title, description, status, deadline, yougile_card_id
                   FROM tasks WHERE responsible_telegram_id = ?
                   ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, deadline_timestamp ASC""",
                (telegram_id,)
            ).fetchall()
    return [dict(row) for row in rows]

def get_task_by_id(task_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

def get_all_active_tasks() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, title, deadline_timestamp, responsible_telegram_id, chat_id
               FROM tasks WHERE status = 'pending' AND deadline_timestamp IS NOT NULL"""
        ).fetchall()
        return [dict(row) for row in rows]

def get_tasks_with_upcoming_deadline(hours_before: int = 2) -> List[Dict[str, Any]]:
    now_ms = int(datetime.now().timestamp() * 1000)
    threshold_ms = now_ms + hours_before * 3_600_000
    return [t for t in get_all_active_tasks()
            if t["deadline_timestamp"] and now_ms < t["deadline_timestamp"] <= threshold_ms]

def complete_task(task_id: str) -> None:
    task = get_task_by_id(task_id)
    if not task:
        return
    responsible_id = task["responsible_telegram_id"]
    with _connect() as conn:
        conn.execute("UPDATE tasks SET status = 'completed', completed_at = ? WHERE id = ?",
                     (datetime.now().isoformat(), task_id))
    update_user_stats(responsible_id, xp_delta=10, tasks_completed_delta=1)
    new_achievements = []
    with _connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE responsible_telegram_id = ? AND status = 'completed'",
            (responsible_id,)
        ).fetchone()[0]
    if count >= 3:
        new_achievements.append("Спринтер")
    stats = get_user_stats(responsible_id)
    if stats["level"] >= 2:
        new_achievements.append("Мастер")
    if new_achievements:
        update_user_stats(responsible_id, achievements_to_add=new_achievements)

def delete_task(task_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    with _connect() as conn:
        conn.execute("DELETE FROM task_history WHERE task_id = ?", (task_id,))

def get_average_completion_time(telegram_id: int) -> Optional[float]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT created_at, completed_at FROM tasks
               WHERE responsible_telegram_id = ? AND status = 'completed'
               AND completed_at IS NOT NULL AND created_at IS NOT NULL
               ORDER BY completed_at DESC LIMIT 5""",
            (telegram_id,)
        ).fetchall()
    if not rows:
        return None
    total_hours = 0.0
    for row in rows:
        created = datetime.fromisoformat(row["created_at"])
        completed = datetime.fromisoformat(row["completed_at"])
        total_hours += (completed - created).total_seconds() / 3600
    return total_hours / len(rows)

def get_stale_tasks(days_old: int = 3) -> List[Dict[str, Any]]:
    threshold = (datetime.now() - timedelta(days=days_old)).isoformat()
    with _connect() as conn:
        rows = conn.execute("""
            SELECT t.id, t.title, t.responsible_telegram_id, t.created_at
            FROM tasks t
            WHERE t.status != 'completed'
              AND (
                SELECT MAX(h.changed_at)
                FROM task_history h
                WHERE h.task_id = t.id
              ) < ?
        """, (threshold,)).fetchall()
        return [dict(row) for row in rows]

# --- Геймификация ---
def get_user_stats(telegram_id: int) -> Dict[str, Any]:
    with _connect() as conn:
        row = conn.execute("SELECT xp, level, achievements FROM user_stats WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if not row:
            return {"xp": 0, "level": 1, "achievements": []}
        return {
            "xp": row["xp"],
            "level": row["level"],
            "achievements": json.loads(row["achievements"]) if row["achievements"] else []
        }

def update_user_stats(telegram_id: int, xp_delta: int = 0, achievements_to_add: List[str] = None,
                      tasks_completed_delta: int = 0, tasks_created_delta: int = 0) -> None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT xp, level, achievements, tasks_completed, tasks_created FROM user_stats WHERE telegram_id = ?",
            (telegram_id,)
        ).fetchone()
        if row:
            new_xp = row["xp"] + xp_delta
            new_level = 1 + (new_xp // 100)
            achievements = json.loads(row["achievements"]) if row["achievements"] else []
            if achievements_to_add:
                for ach in achievements_to_add:
                    if ach not in achievements:
                        achievements.append(ach)
            new_tasks_completed = row["tasks_completed"] + tasks_completed_delta
            new_tasks_created = row["tasks_created"] + tasks_created_delta
            conn.execute(
                """UPDATE user_stats SET xp = ?, level = ?, achievements = ?,
                    tasks_completed = ?, tasks_created = ? WHERE telegram_id = ?""",
                (new_xp, new_level, json.dumps(achievements), new_tasks_completed, new_tasks_created, telegram_id)
            )
        else:
            achievements = achievements_to_add if achievements_to_add else []
            conn.execute(
                """INSERT INTO user_stats (telegram_id, xp, level, achievements, tasks_completed, tasks_created)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (telegram_id, xp_delta, 1 + (xp_delta // 100), json.dumps(achievements), tasks_completed_delta, tasks_created_delta)
            )

def get_telegram_id_by_username(username: str) -> Optional[int]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT telegram_id FROM users WHERE username = ?", (username,)
        ).fetchone()
        return row["telegram_id"] if row else None

# --- Расширенный трекинг скорости и качества ---
def get_on_time_completion_rate(telegram_id: int) -> float:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT deadline_timestamp, completed_at FROM tasks WHERE responsible_telegram_id = ? AND status = 'completed' AND deadline_timestamp IS NOT NULL",
            (telegram_id,)
        ).fetchall()
    if not rows:
        return 0.0
    on_time = 0
    for row in rows:
        deadline_ts = row["deadline_timestamp"] / 1000
        try:
            completed_ts = datetime.fromisoformat(row["completed_at"]).timestamp()
        except (TypeError, ValueError):
            continue
        if completed_ts <= deadline_ts:
            on_time += 1
    return (on_time / len(rows)) * 100

def get_average_time_in_progress(telegram_id: int) -> Optional[float]:
    """Среднее время в статусе 'in_progress' (часы)."""
    with _connect() as conn:
        task_rows = conn.execute(
            "SELECT id FROM tasks WHERE responsible_telegram_id = ? AND status = 'completed'",
            (telegram_id,)
        ).fetchall()
        if not task_rows:
            return None
        total_hours = 0.0
        count = 0
        for row in task_rows:
            task_id = row["id"]
            entry = conn.execute(
                "SELECT changed_at FROM task_history WHERE task_id = ? AND status_to = 'in_progress' ORDER BY changed_at ASC LIMIT 1",
                (task_id,)
            ).fetchone()
            exit_ = conn.execute(
                "SELECT changed_at FROM task_history WHERE task_id = ? AND status_to = 'completed' ORDER BY changed_at ASC LIMIT 1",
                (task_id,)
            ).fetchone()
            if entry and exit_:
                entry_time = datetime.fromisoformat(entry["changed_at"])
                exit_time = datetime.fromisoformat(exit_["changed_at"])
                total_hours += (exit_time - entry_time).total_seconds() / 3600
                count += 1
    return total_hours / count if count > 0 else None

def get_task_status_counts(telegram_id: int) -> Dict[str, int]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM tasks WHERE responsible_telegram_id = ? GROUP BY status",
            (telegram_id,)
        ).fetchall()
    return {row["status"]: row["cnt"] for row in rows}