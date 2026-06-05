import re
from typing import Optional
from . import date_utils

_TASK_KEYWORDS = frozenset([
    # Общие маркеры
    "задача", "задачи", "таск", "task", "поручение",
    "дедлайн", "срок", "крайний", "план", "планируется",

    # Необходимость
    "нужно", "надо", "необходимо", "следует",
    "требуется", "обязательно", "желательно",
    "нужен", "нужна", "нужно", "нужны",

    # Создание
    "сделать", "сделай", "создать", "создай",
    "разработать", "разработай",
    "реализовать", "реализуй",
    "написать", "напиши",
    "подготовить", "подготовь",
    "сформировать", "сформируй",
    "составить", "составь",
    "собрать", "собери",
    "оформить", "оформи",
    "заполнить", "заполни",

    # Изменение
    "обновить", "обнови",
    "исправить", "исправь",
    "доработать", "доработай",
    "переработать", "переработай",
    "изменить", "измени",
    "добавить", "добавь",
    "удалить", "удали",
    "оптимизировать", "оптимизируй",
    "улучшить", "улучши",
    "обновление",

    # Проверка
    "проверить", "проверь",
    "протестировать", "протестируй",
    "отладить", "отладь",
    "проанализировать", "проанализируй",
    "ревью", "review",
    "проверка", "тестирование",

    # Документы
    "отчет", "отчёт",
    "презентация", "презентацию",
    "документ", "документация",
    "спецификация", "тз",
    "сводка", "макет",
    "схема", "инструкция",

    # Коммуникации
    "отправить", "отправь",
    "выслать", "вышли",
    "согласовать", "согласуй",
    "обсудить", "обсуди",
    "созвониться", "созвон",
    "встретиться", "встреча",
    "уведомить", "сообщить",

    # Организация
    "организовать", "организуй",
    "провести", "проведи",
    "назначить", "назначь",
    "забронировать", "забронируй",
    "подготовка",

    # Покупки и ресурсы
    "купить", "заказать",
    "закупить", "приобрести",

    # Разработка
    "фича", "feature",
    "баг", "bug",
    "фикс", "fix",
    "рефакторинг",
    "деплой", "deploy",
    "релиз", "release",
    "миграция",
    "интеграция",

    # Канбан-маркеры
    "в работу",
    "выполнить", "выполни",
    "завершить", "заверши",
    "закрыть", "закрой",
    "взять",
    "перенести",
    "приоритет",

    # Напоминания
    "не забудь",
    "напомни",
    "помни",

    # Временные маркеры
    "до",
    "к",
    "сегодня",
    "завтра",
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье"
])

def parse_task(text: str, known_usernames: list[str]) -> dict:
    text_lower = text.lower()
    # 1. Находим всех @упомянутых
    assignees = re.findall(r'@([a-zA-Z0-9_]+)', text)
    # 2. Дедлайн
    deadline = date_utils.parse_deadline(text)
    # 3. Текст задачи (удаляем все @упоминания и дедлайн)
    task = text.strip()
    for assignee in assignees:
        task = re.sub(rf'@?{re.escape(assignee)}\b', '', task, flags=re.IGNORECASE)
    if deadline:
        task = re.sub(re.escape(deadline), '', task, flags=re.IGNORECASE)
    task = re.sub(r'\s+', ' ', task).strip(' ,.-:')
    if not task:
        task = text.strip()
    # 4. Confidence
    confidence = 90 if (assignees and deadline) else 75 if (assignees or deadline) else 50
    if len(task) < 5:
        confidence = 0
    return {
        "task": task,
        "deadline": deadline,
        "assignees": assignees,   # список строк
        "confidence": confidence,
    }

def _calculate_confidence(task: str, deadline: Optional[str], assignee: Optional[str], text_lower: str) -> int:
    has_task = len(task) > 5
    has_deadline = deadline is not None
    has_assignee = assignee is not None
    has_keyword = any(re.search(rf'\b{kw}\b', text_lower) for kw in _TASK_KEYWORDS)

    if not has_keyword and not has_deadline and not has_assignee:
        return 0
    if len(text_lower.split()) <= 3 and not has_deadline and not has_assignee:
        return 0
    if has_keyword and not has_task:
        return 30
    if has_task and has_deadline and has_assignee:
        return 90
    if has_task and (has_deadline or has_assignee):
        return 75
    if has_task:
        return 55
    return 30