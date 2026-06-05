import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

DB_PATH = Path(__file__).parent / "tasks.db"


def init_db() -> None:
    """Создаёт таблицы задач и пользователей, если их нет."""
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
        ''')
        
        # Миграция: добавляем completed_at, если её нет (для существующих БД)
        try:
            conn.execute("ALTER TABLE tasks ADD COLUMN completed_at TEXT")
        except sqlite3.OperationalError:
            pass  # Колонка уже существует

@contextmanager
def _connect() -> Generator[sqlite3.Connection, None, None]:
    """Контекстный менеджер: открывает соединение с БД и закрывает после блока."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Инициализируем БД при первом импорте модуля
init_db()


# ── Пользователи ──────────────────────────────────────────────────────────────

def add_user(
    telegram_id: int,
    username: Optional[str] = None,
    full_name: Optional[str] = None,
) -> None:
    """Добавляет пользователя в БД, если его ещё нет."""
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, full_name) VALUES (?, ?, ?)",
            (telegram_id, username, full_name),
        )


def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Возвращает данные пользователя или None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    return dict(row) if row else None


def set_user_away(telegram_id: int, reason: str, until: Optional[datetime] = None) -> None:
    """Помечает пользователя как недоступного."""
    until_str = until.isoformat() if until else None
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET is_away = 1, away_reason = ?, away_until = ? WHERE telegram_id = ?",
            (reason, until_str, telegram_id),
        )


def clear_user_away(telegram_id: int) -> None:
    """Снимает статус недоступности с пользователя."""
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET is_away = 0, away_reason = NULL, away_until = NULL WHERE telegram_id = ?",
            (telegram_id,),
        )


def get_pending_user_ids() -> List[int]:
    """Возвращает список telegram_id пользователей, у которых есть активные задачи."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT responsible_telegram_id FROM tasks WHERE status = 'pending'"
        ).fetchall()
    return [row["responsible_telegram_id"] for row in rows]


# ── Задачи ────────────────────────────────────────────────────────────────────

def add_task(
    task_id: str,
    title: str,
    description: str,
    responsible_telegram_id: int,
    deadline: Optional[str] = None,
    deadline_timestamp: Optional[int] = None,
    yougile_card_id: Optional[str] = None,
    chat_id: Optional[int] = None,
) -> None:
    """Сохраняет новую задачу в БД."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO tasks
                (id, title, description, status, deadline, deadline_timestamp,
                 responsible_telegram_id, yougile_card_id, chat_id, created_at)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id, title, description, deadline, deadline_timestamp,
                responsible_telegram_id, yougile_card_id, chat_id,
                datetime.now().isoformat(),
            ),
        )


def get_tasks_by_user(
    telegram_id: int,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Возвращает задачи пользователя, опционально фильтруя по статусу."""
    with _connect() as conn:
        if status:
            rows = conn.execute(
                """
                SELECT id, title, description, status, deadline, yougile_card_id
                FROM tasks
                WHERE responsible_telegram_id = ? AND status = ?
                ORDER BY deadline_timestamp ASC
                """,
                (telegram_id, status),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, title, description, status, deadline, yougile_card_id
                FROM tasks
                WHERE responsible_telegram_id = ?
                ORDER BY
                    CASE status WHEN 'pending' THEN 0 ELSE 1 END,
                    deadline_timestamp ASC
                """,
                (telegram_id,),
            ).fetchall()
    return [dict(row) for row in rows]

def get_task_by_id(task_id: str) -> Optional[Dict[str, Any]]:
    """Возвращает задачу по ID или None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return dict(row) if row else None


def get_all_active_tasks() -> List[Dict[str, Any]]:
    """Возвращает все активные задачи с дедлайном (для планировщика напоминаний)."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, title, deadline_timestamp, responsible_telegram_id, chat_id
            FROM tasks
            WHERE status = 'pending' AND deadline_timestamp IS NOT NULL
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_tasks_with_upcoming_deadline(hours_before: int = 2) -> List[Dict[str, Any]]:
    """Возвращает задачи, дедлайн которых наступит в течение hours_before часов."""
    now_ms = int(datetime.now().timestamp() * 1000)
    threshold_ms = now_ms + hours_before * 3_600_000
    return [
        t for t in get_all_active_tasks()
        if t["deadline_timestamp"] and now_ms < t["deadline_timestamp"] <= threshold_ms
    ]


def complete_task(task_id: str) -> None:
    """Помечает задачу как выполненную и записывает время завершения."""
    with _connect() as conn:
        conn.execute(
            "UPDATE tasks SET status = 'completed', completed_at = ? WHERE id = ?",
            (datetime.now().isoformat(), task_id),
        )


def delete_task(task_id: str) -> None:
    """Удаляет задачу из БД."""
    with _connect() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))





def get_average_completion_time() -> Optional[float]:
    """Возвращает среднее время выполнения задач в часах или None."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT created_at, completed_at
            FROM tasks
            WHERE status = 'completed' AND completed_at IS NOT NULL AND created_at IS NOT NULL
            """
        ).fetchall()
        
        if not rows:
            return None
        
        total_hours = 0.0
        count = 0
        for row in rows:
            try:
                created = datetime.fromisoformat(row["created_at"])
                completed = datetime.fromisoformat(row["completed_at"])
                hours = (completed - created).total_seconds() / 3600
                if hours > 0:  # Игнорируем отрицательные значения
                    total_hours += hours
                    count += 1
            except (ValueError, TypeError):
                continue
        
        return total_hours / count if count > 0 else None
    

    from datetime import timedelta

def get_stale_tasks(days_old: int = 3) -> List[Dict[str, Any]]:
    """Возвращает задачи, которые находятся в статусе pending дольше days_old дней."""
    threshold = (datetime.now() - timedelta(days=days_old)).isoformat()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, title, responsible_telegram_id, created_at
            FROM tasks
            WHERE status = 'pending' AND created_at < ?
            """,
            (threshold,),
        ).fetchall()
        return [dict(row) for row in rows]
        