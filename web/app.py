import os
import sys
from html import escape

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

# При запуске напрямую (python web/app.py) корень проекта не в sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from web.database import get_tasks_by_user, complete_task, delete_task

app = FastAPI(title="PM Assist — Личный кабинет")

# Фигурные скобки в CSS экранированы двойными {{ }} для совместимости с str.format()
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
        .tasks-section {{
            background: white; border-radius: 15px; padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }}
        .tasks-title {{ font-size: 24px; margin-bottom: 20px; color: #333; }}
        .task-table {{ width: 100%; border-collapse: collapse; }}
        .task-table th {{
            text-align: left; padding: 15px;
            background: #f8f9fa; border-bottom: 2px solid #dee2e6;
        }}
        .task-table td {{ padding: 15px; border-bottom: 1px solid #dee2e6; }}
        .status-pending {{
            background: #fff3cd; color: #856404;
            padding: 5px 12px; border-radius: 20px; display: inline-block;
        }}
        .status-completed {{
            background: #d4edda; color: #155724;
            padding: 5px 12px; border-radius: 20px; display: inline-block;
        }}
        .btn {{
            padding: 8px 16px; border: none; border-radius: 6px;
            cursor: pointer; font-size: 14px; margin: 0 5px;
        }}
        .btn-complete {{ background: #28a745; color: white; }}
        .btn-complete:hover {{ background: #218838; }}
        .btn-delete {{ background: #dc3545; color: white; }}
        .btn-delete:hover {{ background: #c82333; }}
        .empty-state {{ text-align: center; padding: 50px; color: #999; }}
        .telegram-id {{
            background: #f0f0f0; padding: 10px;
            border-radius: 8px; margin-top: 15px;
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>📋 PM Assist — Личный кабинет</h1>
        <p>Ваш персональный помощник по задачам</p>
        <div class="telegram-id">🔑 Ваш ID в Telegram: <strong>{telegram_id}</strong></div>
    </div>
    <div class="stats">
        <div class="stat-card">
            <div class="stat-number">{total}</div>
            <div class="stat-label">Всего задач</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{pending}</div>
            <div class="stat-label">В работе</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{completed}</div>
            <div class="stat-label">Выполнено</div>
        </div>
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
            f'<button type="submit" class="btn btn-delete" '
            f"onclick=\"return confirm('Удалить задачу?')\">🗑 Удалить</button>"
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
    return HTMLResponse(
        _HTML_TEMPLATE.format(
            telegram_id=telegram_id,
            total=total,
            pending=pending,
            completed=completed,
            tasks_table=_build_tasks_table(tasks, telegram_id),
        )
    )


@app.post("/task/{task_id}/complete")
async def task_complete(task_id: str, telegram_id: int = Form(...)) -> RedirectResponse:
    complete_task(task_id)
    return RedirectResponse(url=f"/cabinet/{telegram_id}", status_code=303)


@app.post("/task/{task_id}/delete")
async def task_delete(task_id: str, telegram_id: int = Form(...)) -> RedirectResponse:
    delete_task(task_id)
    return RedirectResponse(url=f"/cabinet/{telegram_id}", status_code=303)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "message": "PM Assist работает"}


if __name__ == "__main__":
    import uvicorn
    print("🚀 Запуск личного кабинета PM Assist")
    print("📱 Откройте в браузере: http://localhost:8000/cabinet/YOUR_TELEGRAM_ID")
    uvicorn.run(app, host="0.0.0.0", port=8000)