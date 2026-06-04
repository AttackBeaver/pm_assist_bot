import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

DB_PATH = Path(__file__).parent / "tasks.db"

def init_db():
    """Создаёт таблицы задач и пользователей, если их нет."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'pending',
            deadline TEXT,
            deadline_timestamp INTEGER,   -- добавлено для напоминаний
            responsible_telegram_id INTEGER,
            yougile_card_id TEXT,         -- сохранение ID из YouGile
            chat_id INTEGER,
            created_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            is_away INTEGER DEFAULT 0,
            away_reason TEXT,
            away_until TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_user(telegram_id: int, username: str = None, full_name: str = None):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (telegram_id, username, full_name)
        VALUES (?, ?, ?)
    ''', (telegram_id, username, full_name))
    conn.commit()
    conn.close()

def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def set_user_away(telegram_id: int, reason: str, until: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users SET is_away = 1, away_reason = ?, away_until = ?
        WHERE telegram_id = ?
    ''', (reason, until, telegram_id))
    conn.commit()
    conn.close()

def clear_user_away(telegram_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users SET is_away = 0, away_reason = NULL, away_until = NULL
        WHERE telegram_id = ?
    ''', (telegram_id,))
    conn.commit()
    conn.close()

def add_task(task_id: str, title: str, description: str, responsible_telegram_id: int,
             deadline: str = None, deadline_timestamp: int = None,
             yougile_card_id: str = None, chat_id: int = None):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO tasks (id, title, description, status, deadline, deadline_timestamp,
                          responsible_telegram_id, yougile_card_id, chat_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (task_id, title, description, 'pending', deadline, deadline_timestamp,
          responsible_telegram_id, yougile_card_id, chat_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_tasks_by_user(telegram_id: int, status: str = None):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if status:
        cursor.execute('''
            SELECT id, title, description, status, deadline, yougile_card_id
            FROM tasks
            WHERE responsible_telegram_id = ? AND status = ?
            ORDER BY deadline_timestamp ASC
        ''', (telegram_id, status))
    else:
        cursor.execute('''
            SELECT id, title, description, status, deadline, yougile_card_id
            FROM tasks
            WHERE responsible_telegram_id = ?
            ORDER BY 
                CASE status WHEN 'pending' THEN 0 ELSE 1 END,
                deadline_timestamp ASC
        ''', (telegram_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_all_active_tasks():
    """Все активные задачи (для напоминаний, без фильтра по пользователю)"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, title, description, deadline_timestamp, responsible_telegram_id, chat_id
        FROM tasks
        WHERE status = 'pending' AND deadline_timestamp IS NOT NULL
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_tasks_with_upcoming_deadline(hours_before: int = 2):
    """Задачи, у которых дедлайн в ближайшие hours_before часов."""
    now_ms = int(datetime.now().timestamp() * 1000)
    threshold_ms = now_ms + hours_before * 3600 * 1000
    tasks = get_all_active_tasks()
    upcoming = []
    for t in tasks:
        if t['deadline_timestamp'] and now_ms < t['deadline_timestamp'] <= threshold_ms:
            upcoming.append(t)
    return upcoming

def complete_task(task_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE tasks SET status = "completed" WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()

def delete_task(task_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()