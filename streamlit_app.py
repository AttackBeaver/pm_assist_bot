import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
import os

from config import YOUGILE_TOKEN, YOUGILE_BOARD_ID, YOUGILE_DONE_COLUMN_ID, YOUGILE_DO_COLUMN_ID
from yougile_client import YouGileClient
from web.database import (
    get_tasks_by_user, get_user_stats, update_user_stats,
    get_average_completion_time, get_on_time_completion_rate,
    get_average_time_in_progress, get_task_status_counts,
    complete_task, delete_task, add_user
)

st.set_page_config(page_title="PM Assist — Личный кабинет", page_icon="📋", layout="wide")

# --- Чтение telegram_id из URL параметра ---
query_params = st.query_params
telegram_id = query_params.get("id", None)
if telegram_id is not None:
    try:
        telegram_id = int(telegram_id)
    except ValueError:
        telegram_id = None

if telegram_id is None:
    st.title("📋 PM Assist — Личный кабинет")
    st.warning("Telegram ID не указан в ссылке.")
    id_input = st.text_input("Введите ваш Telegram ID", value="", key="telegram_id_input")
    if id_input and id_input.isdigit():
        telegram_id = int(id_input)
        st.query_params.update({"id": telegram_id})
        st.rerun()
    else:
        st.info("Введите ID, который вы получили от бота (команда /start)")
        st.stop()
else:
    st.title("📋 PM Assist — Личный кабинет")
    st.caption(f"Вы вошли как пользователь с ID: {telegram_id}")

# --- Регистрация пользователя ---
add_user(telegram_id, username="streamlit_user", full_name="Пользователь Streamlit")

# --- Боковая панель ---
st.sidebar.header("Пользователь")
stats = get_user_stats(telegram_id)
xp = stats["xp"]
level = stats["level"]
achievements = stats.get("achievements", [])
st.sidebar.metric("✨ Опыт (XP)", f"{xp}")
st.sidebar.metric("🧙‍♂️ Уровень", f"{level}")

if achievements:
    st.sidebar.markdown("**🏆 Достижения**")
    for ach in achievements:
        st.sidebar.text(f"• {ach}")
else:
    st.sidebar.info("Пока нет достижений. Выполняйте задачи!")

# --- Основная статистика ---
tasks = get_tasks_by_user(telegram_id)
total_tasks = len(tasks)
completed_tasks = sum(1 for t in tasks if t["status"] == "completed")
pending_tasks = total_tasks - completed_tasks

col1, col2, col3, col4 = st.columns(4)
col1.metric("Всего задач", total_tasks)
col2.metric("В работе", pending_tasks)
col3.metric("Выполнено", completed_tasks)
avg_time = get_average_completion_time(telegram_id)
col4.metric("Среднее время, ч", f"{avg_time:.1f}" if avg_time else "—")

# --- Расширенная аналитика ---
with st.expander("📈 Аналитика эффективности", expanded=False):
    on_time_rate = get_on_time_completion_rate(telegram_id)
    avg_progress = get_average_time_in_progress(telegram_id) or 0.0
    status_counts = get_task_status_counts(telegram_id)
    pending_cnt = status_counts.get("pending", 0)
    completed_cnt = status_counts.get("completed", 0)
    in_progress_cnt = status_counts.get("in_progress", 0)
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("✅ Выполнено в срок", f"{on_time_rate:.1f}%")
    col_b.metric("⏱ Среднее время в работе", f"{avg_progress:.1f} ч")
    col_c.markdown(f"**Статусы задач:**\n- 🟡 В процессе: {in_progress_cnt}\n- 🟢 Выполнено: {completed_cnt}\n- ⚪ Ожидают: {pending_cnt}")

# --- Таблица задач ---
st.subheader("📌 Мои задачи")
if not tasks:
    st.info("✨ У вас пока нет задач. Напишите боту в Telegram, чтобы создать задачу.")
else:
    df = pd.DataFrame(tasks)
    df = df[["title", "description", "deadline", "status"]]
    df.columns = ["Задача", "Описание", "Дедлайн", "Статус"]
    st.dataframe(df, use_container_width=True)

    st.markdown("---")
    st.subheader("🛠 Управление задачами")
    pending_tasks_list = [t for t in tasks if t["status"] != "completed"]
    if not pending_tasks_list:
        st.success("Все задачи выполнены! Отличная работа!")
    else:
        for task in pending_tasks_list:
            with st.container():
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                col1.markdown(f"**{task['title']}**  \n*{task['description'] or '—'}*  \n⏰ Дедлайн: {task['deadline'] or 'не указан'}")
                if col2.button(f"✅ Выполнить", key=f"complete_{task['id']}"):
                    if YOUGILE_TOKEN and YOUGILE_BOARD_ID and task.get("yougile_card_id"):
                        client = YouGileClient(YOUGILE_TOKEN)
                        success = client.move_task(task["yougile_card_id"], YOUGILE_DONE_COLUMN_ID)
                        if success:
                            complete_task(task["id"])
                            st.success(f"Задача «{task['title']}» выполнена и перемещена в «Готово»")
                            st.rerun()
                        else:
                            st.error("Ошибка при завершении задачи в YouGile")
                    else:
                        complete_task(task["id"])
                        st.success(f"Задача «{task['title']}» отмечена выполненной локально")
                        st.rerun()
                if col3.button(f"🗑 Удалить", key=f"delete_{task['id']}"):
                    if YOUGILE_TOKEN and task.get("yougile_card_id"):
                        client = YouGileClient(YOUGILE_TOKEN)
                        success = client.delete_task(task["yougile_card_id"])
                        if success:
                            delete_task(task["id"])
                            st.success(f"Задача «{task['title']}» удалена из YouGile и локально")
                            st.rerun()
                        else:
                            st.error("Ошибка удаления в YouGile")
                    else:
                        delete_task(task["id"])
                        st.success(f"Задача «{task['title']}» удалена локально")
                        st.rerun()
                if col4.button(f"▶️ Взять в работу", key=f"move_{task['id']}"):
                    if YOUGILE_TOKEN and task.get("yougile_card_id"):
                        client = YouGileClient(YOUGILE_TOKEN)
                        if YOUGILE_DO_COLUMN_ID:
                            success = client.move_task(task["yougile_card_id"], YOUGILE_DO_COLUMN_ID)
                            if success:
                                st.success(f"Задача «{task['title']}» перемещена в работу")
                                st.rerun()
                            else:
                                st.error("Ошибка перемещения")
                        else:
                            st.warning("ID колонки 'В процессе' не задан")
                    else:
                        st.warning("YouGile не настроен")

st.sidebar.markdown("---")
st.sidebar.caption("Данные хранятся локально. Для полной синхронизации с YouGile требуется настройка API.")
st.sidebar.caption(f"Текущий пользователь: {telegram_id}")