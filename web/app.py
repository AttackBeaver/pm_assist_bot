﻿import os
import sys
from html import escape
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from web.database import (
    get_tasks_by_user, complete_task, delete_task, get_user_stats,
    get_average_completion_time, get_task_by_id,
    get_on_time_completion_rate, get_average_time_in_progress, get_task_status_counts
)
from yougile_client import YouGileClient
from config import YOUGILE_TOKEN, YOUGILE_DONE_COLUMN_ID, YOUGILE_BOARD_ID

logger = logging.getLogger(__name__)
app = FastAPI(title="PM Assist — Личный кабинет")

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PM Assist — Мой кабинет</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{
            background: white; border-radius: 15px; padding: 25px;
            margin-bottom: 25px; box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }}
        .header h1 {{ color: #333; margin-bottom: 10px; }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px; margin-bottom: 30px;
        }}
        .stat-card {{
            background: white; border-radius: 10px; padding: 20px;
            text-align: center; box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        .stat-number {{ font-size: 36px; font-weight: bold; color: #667eea; }}
        .stat-label {{ color: #666; margin-top: 5px; }}
        .level-card {{
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
        }}
        .level-card .stat-number {{ color: white; }}
        .tasks-section {{
            background: white; border-radius: 15px; padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }}
        .tasks-title {{ font-size: 24px; margin-bottom: 20px; color: #333; }}
        .task-table {{ width: 100%; border-collapse: collapse; }}
        .task-table th {{ text-align: left; padding: 15px; background: #f8f9fa; border-bottom: 2px solid #dee2e6; }}
        .task-table td {{ padding: 15px; border-bottom: 1px solid #dee2e6; }}
        .status-pending {{ background: #fff3cd; color: #856404; padding: 5px 12px; border-radius: 20px; display: inline-block; }}
        .status-completed {{ background: #d4edda; color: #155724; padding: 5px 12px; border-radius: 20px; display: inline-block; }}
        .btn {{ padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; margin: 0 5px; }}
        .btn-complete {{ background: #28a745; color: white; }}
        .btn-complete:hover {{ background: #218838; }}
        .btn-delete {{ background: #dc3545; color: white; }}
        .btn-delete:hover {{ background: #c82333; }}
        .empty-state {{ text-align: center; padding: 50px; color: #999; }}
        .telegram-id {{
            background: #f0f0f0; padding: 10px;
            border-radius: 8px; margin-top: 15px;
        }}
        .achievements-block {{
            margin-top: 20px; padding: 15px; background: #f8f9fa;
            border-radius: 10px; text-align: center;
        }}
        .achievements-title {{ font-size: 18px; margin-bottom: 10px; color: #333; }}
        .user-level {{ display: inline-block; margin-left: 20px; padding: 5px 15px; background: #667eea; color: white; border-radius: 20px; }}
        .analytics-block {{
            background: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
        }}
        .analytics-title {{
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        .stats-mini {{
            display: flex;
            gap: 20px;
            margin-bottom: 10px;
        }}
        .stat-mini .stat-value {{
            font-size: 24px;
            font-weight: bold;
            color: #667eea;
        }}
        .status-distribution {{
            display: flex;
            gap: 15px;
            font-size: 14px;
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>📋 PM Assist — Личный кабинет</h1>
        <p>Ваш персональный помощник по задачам</p>
        <div class="telegram-id">
            🔑 Ваш ID в Telegram: <strong>{telegram_id}</strong>
            <span class="user-level">🧙‍♂️ Уровень {level} | ✨ {xp} XP</span>
        </div>
    </div>
    <div class="stats">
        <div class="stat-card"><div class="stat-number">{total}</div><div class="stat-label">Всего задач</div></div>
        <div class="stat-card"><div class="stat-number">{pending}</div><div class="stat-label">В работе</div></div>
        <div class="stat-card"><div class="stat-number">{completed}</div><div class="stat-label">Выполнено</div></div>
        <div class="stat-card"><div class="stat-number">{avg_time}</div><div class="stat-label">Среднее время, ч</div></div>
    </div>
    <div class="analytics-block">
        <div class="analytics-title">📈 Аналитика эффективности</div>
        <div class="stats-mini">
            <div class="stat-mini"><span class="stat-value">{on_time_rate:.1f}%</span> задач выполнено в срок</div>
            <div class="stat-mini"><span class="stat-value">{avg_progress_time:.1f} ч</span> среднее время в работе</div>
        </div>
        <div class="status-distribution">
            {status_distribution_html}
        </div>
    </div>
    <div class="achievements-block">
        <div class="achievements-title">🏆 Достижения</div>
        <div>{achievements_html}</div>
    </div>
    <div class="tasks-section">
        <h2 class="tasks-title">📌 Мои задачи</h2>
        {tasks_table}
    </div>
</div>
</body>
</html>
"""

def _build_tasks_table(tasks: list, telegram_id: int) -> str:
    if not tasks:
        return (
            '<div class="empty-state">'
            "<p>✨ У вас пока нет задач</p>"
            '<p>Напишите боту в Telegram: <strong>«Имя, задача до даты»</strong></p>'
            "</div>"
        )
    rows = []
    for task in tasks:
        is_completed = task["status"] == "completed"
        status_class = "status-completed" if is_completed else "status-pending"
        status_text = "✅ Выполнено" if is_completed else "🟡 В работе"
        task_id = escape(task["id"])
        tid = escape(str(telegram_id))
        actions = ""
        if not is_completed:
            actions += (
                f'<form method="post" action="/task/{task_id}/complete" style="display:inline">'
                f'<input type="hidden" name="telegram_id" value="{tid}">'
                f'<button type="submit" class="btn btn-complete">✓ Выполнить</button>'
                f"</form>"
            )
        actions += (
            f'<form method="post" action="/task/{task_id}/delete" style="display:inline">'
            f'<input type="hidden" name="telegram_id" value="{tid}">'
            f'<button type="submit" class="btn btn-delete" onclick="return confirm(\'Удалить задачу?\')">🗑 Удалить</button>'
            f"</form>"
        )
        rows.append(
            f"<tr>"
            f"<td><strong>{escape(task['title'])}</strong></td>"
            f"<td>{escape(task['description'] or '—')}</td>"
            f"<td>{escape(task['deadline'] or '—')}</td>"
            f'<td><span class="{status_class}">{status_text}</span></td>'
            f"<td>{actions}</td>"
            f"</tr>"
        )
    return (
        '<table class="task-table">'
        "<thead><tr>"
        "<th>Задача</th><th>Описание</th><th>Дедлайн</th><th>Статус</th><th>Действия</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )

@app.get("/cabinet/{telegram_id}", response_class=HTMLResponse)
async def cabinet(telegram_id: int) -> HTMLResponse:
    tasks = get_tasks_by_user(telegram_id)
    total = len(tasks)
    completed = sum(1 for t in tasks if t["status"] == "completed")
    pending = total - completed
    avg_time = get_average_completion_time(telegram_id)
    avg_time_str = f"{avg_time:.1f}" if avg_time else "—"
    stats = get_user_stats(telegram_id)
    xp = stats["xp"]
    level = stats["level"]
    achievements = stats["achievements"]
    achievements_html = ''
    for ach in achievements:
        icon = "🏆"
        if "Первая" in ach:
            icon = "🎯"
        elif "Спринтер" in ach:
            icon = "⚡"
        elif "Мастер" in ach:
            icon = "🧙"
        achievements_html += f'<div style="display: inline-block; margin: 5px; text-align: center;">' \
                             f'<div style="font-size: 30px;">{icon}</div>' \
                             f'<div style="font-size: 12px;">{ach}</div></div>'
    if not achievements_html:
        achievements_html = '<div style="color: #999;">Пока нет достижений. Выполняйте задачи!</div>'
    
    # Расширенная аналитика
    on_time_rate = get_on_time_completion_rate(telegram_id)
    avg_progress_time = get_average_time_in_progress(telegram_id) or 0.0
    status_counts = get_task_status_counts(telegram_id)
    pending_count = status_counts.get("pending", 0)
    completed_count = status_counts.get("completed", 0)
    in_progress_count = status_counts.get("in_progress", 0)
    status_distribution_html = f'<span>🟡 В работе: {in_progress_count}</span> <span>🟢 Выполнено: {completed_count}</span> <span>⚪ Ожидают: {pending_count}</span>'
    
    return HTMLResponse(
        _HTML_TEMPLATE.format(
            telegram_id=telegram_id,
            total=total,
            pending=pending,
            completed=completed,
            avg_time=avg_time_str,
            xp=xp,
            level=level,
            achievements_html=achievements_html,
            tasks_table=_build_tasks_table(tasks, telegram_id),
            on_time_rate=on_time_rate,
            avg_progress_time=avg_progress_time,
            status_distribution_html=status_distribution_html
        )
    )

@app.post("/task/{task_id}/complete")
async def task_complete(task_id: str, telegram_id: int = Form(...)) -> RedirectResponse:
    task = get_task_by_id(task_id)
    if not task:
        return RedirectResponse(url=f"/cabinet/{telegram_id}?error=not_found", status_code=303)
    # Проверка прав: только ответственный или автор могут выполнить
    if task["responsible_telegram_id"] != telegram_id and task["author_telegram_id"] != telegram_id:
        return RedirectResponse(url=f"/cabinet/{telegram_id}?error=forbidden", status_code=303)
    
    if task.get("yougile_card_id") and YOUGILE_TOKEN:
        try:
            client = YouGileClient(YOUGILE_TOKEN)
            done_column_id = YOUGILE_DONE_COLUMN_ID
            if not done_column_id and YOUGILE_BOARD_ID:
                done_column_id = client.get_column_id_by_title(YOUGILE_BOARD_ID, "Готово")
            if done_column_id:
                client.move_task(task["yougile_card_id"], done_column_id)
            else:
                logger.warning("Не найден ID колонки 'Готово' в YouGile")
        except Exception as e:
            logger.error(f"Ошибка синхронизации с YouGile: {e}")
    complete_task(task_id)
    return RedirectResponse(url=f"/cabinet/{telegram_id}", status_code=303)

@app.post("/task/{task_id}/delete")
async def task_delete(task_id: str, telegram_id: int = Form(...)) -> RedirectResponse:
    task = get_task_by_id(task_id)
    if not task:
        return RedirectResponse(url=f"/cabinet/{telegram_id}?error=not_found", status_code=303)
    # Проверка прав: только автор может удалить
    if task["author_telegram_id"] != telegram_id:
        return RedirectResponse(url=f"/cabinet/{telegram_id}?error=forbidden", status_code=303)
    
    delete_task(task_id)
    return RedirectResponse(url=f"/cabinet/{telegram_id}", status_code=303)

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "message": "PM Assist web is alive"}

@app.get("/ping")
async def ping():
    return {"status": "ok", "message": "PM Assist web is alive"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Запуск личного кабинета на порту {port}")
    uvicorn.run(app, host="127.0.0.1", port=port)