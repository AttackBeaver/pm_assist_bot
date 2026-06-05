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
    assignee = None

    # 1) Поиск @username
    at_mentions = re.findall(r'@([a-zA-Z0-9_]+)', text)
    if at_mentions:
        assignee = at_mentions[0]
    else:
        # 2) Поиск имени с заглавной буквы в начале строки (до запятой, точки или пробела)
        # Пример: "Антон, сделай отчёт" -> "Антон"
        match = re.match(r'^([А-ЯA-Z][а-яa-z]+(?:[-\s][А-ЯA-Z][а-яa-z]+)?)\s*[,.:]?\s+', text)
        if match:
            potential_name = match.group(1)
            # Дополнительно проверим, что имя не слишком короткое и не похоже на команду
            if len(potential_name) >= 2 and not potential_name.lower() in ['я', 'ты', 'он', 'она', 'оно']:
                assignee = potential_name
        else:
            # 3) Поиск email (как вариант, но вряд ли это ответственный)
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
            if email_match:
                assignee = email_match.group(0)  # сохраняем email как строку
    # 2. Дедлайн
    deadline = date_utils.parse_deadline(text)
    # 3. Текст задачи
    task = text.strip()
    if assignee:
        task = re.sub(rf'@?{re.escape(assignee)}\b', '', task, flags=re.IGNORECASE)
    if deadline:
        task = re.sub(re.escape(deadline), '', task, flags=re.IGNORECASE)
    task = re.sub(r'\s+', ' ', task).strip(' ,.-:')
    if not task:
        task = text.strip()
    # 4. Confidence
    confidence = _calculate_confidence(task, deadline, assignee, text_lower)
    if confidence == 0:
        task = ""
    return {
        "task": task,
        "deadline": deadline,
        "assignee": assignee,
        "confidence": confidence,
    }

def _calculate_confidence(task: str, deadline: Optional[str], assignee: Optional[str], text_lower: str) -> int:
    has_task = len(task) > 5
    has_deadline = deadline is not None
    has_assignee = assignee is not None
    has_keyword = any(re.search(rf'\b{kw}\b', text_lower) for kw in _TASK_KEYWORDS)

    # Если нет ключевых слов и нет дедлайна и нет ответственного – уверенность 0
    if not has_keyword and not has_deadline and not has_assignee:
        return 0
    # Если сообщение очень короткое (3 слова или меньше) и нет дедлайна/ответственного – 0
    if len(text_lower.split()) <= 3 and not has_deadline and not has_assignee:
        return 0
    # Если есть ключевое слово, но задача не выделена
    if has_keyword and not has_task:
        return 30
    if has_task and has_deadline and has_assignee:
        return 90
    if has_task and (has_deadline or has_assignee):
        return 75
    if has_task:
        return 55
    return 30