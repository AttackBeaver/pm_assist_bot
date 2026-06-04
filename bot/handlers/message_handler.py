import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.parser import parse_task
from web.database import add_user   # изменён импорт

logger = logging.getLogger(__name__)
router = Router()

# Временное хранилище для неподтверждённых задач
pending_text_tasks = {}

@router.message(F.text, F.chat.type.in_({'group', 'supergroup'}))
async def handle_text_message(message: Message):
    # Регистрируем пользователя, если его нет
    add_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name
    )
    
    # Список известных username (пока пустой, можно расширить)
    known_usernames = []
    
    parse_result = parse_task(message.text, known_usernames)
    
    # Если уверенность низкая – не предлагаем
    if parse_result['confidence'] < 50:
        return
    
    callback_id = f"text_{message.message_id}"
    pending_text_tasks[callback_id] = {
        "title": parse_result['task'],
        "description": message.text,
        "deadline_str": parse_result['deadline'],
        "assignee_username": parse_result['assignee'],
        "chat_id": message.chat.id,
        "message_id": message.message_id,
        "from_user_id": message.from_user.id
    }
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, создать задачу", callback_data=f"confirm_text_{callback_id}")
    builder.button(text="❌ Отмена", callback_data=f"cancel_text_{callback_id}")
    builder.adjust(1)
    
    task_info = f"**Задача:** {parse_result['task']}\n"
    if parse_result['deadline']:
        task_info += f"**Дедлайн:** {parse_result['deadline']}\n"
    if parse_result['assignee']:
        task_info += f"**Ответственный:** @{parse_result['assignee']}\n"
    
    await message.reply(
        f"📝 Найдена задача:\n{task_info}\nСоздать карточку в YouGile?",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )