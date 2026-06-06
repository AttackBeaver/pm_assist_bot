import re
from typing import Optional
from . import date_utils

_TASK_KEYWORDS = frozenset([
    "задача", "задачи", "таск", "task", "поручение",
    "дедлайн", "срок", "крайний", "план", "планируется",
    "нужно", "надо", "необходимо", "следует", "требуется", "обязательно",
    "сделать", "сделай", "создать", "создай", "разработать", "разработай",
    "реализовать", "реализуй", "написать", "напиши", "подготовить", "подготовь",
    "сформировать", "сформируй", "составить", "составь", "собрать", "собери",
    "обновить", "обнови", "исправить", "исправь", "доработать", "доработай",
    "проверить", "проверь", "протестировать", "протестируй", "отладить", "отладь",
    "отчет", "отчёт", "презентация", "презентацию", "документ", "документация",
    "отправить", "отправь", "выслать", "вышли", "согласовать", "согласуй",
    "организовать", "организуй", "провести", "проведи", "назначить", "назначь",
    "купить", "заказать", "рефакторинг", "интеграция", "в работу", "выполнить",
    "выполни", "завершить", "заверши", "закрыть", "закрой", "взять", "перенести",
    "не забудь", "напомни", "помни", "до", "к", "сегодня", "завтра",
])

_STOP_WORDS = frozenset([
    "привет", "здравствуйте", "добрый день", "пока", "до свидания",
    "как дела", "что нового", "спасибо", "извините", "простите",
    "отправь файлы", "скинь файл", "пришли файл", "открой", "закрой",
    "помощь", "help", "инструкция", "правила", "как пользоваться",
    "просто сообщение", "без задач", "без упоминаний",
    "шаблон", "дизайн", "использовать", "обязательно", "просто",
    "все подряд", "?))", ")))", "??", "?)", "ладно", "окей", "ок",
    "ага", "да ну", "неужели", "правда", "интересно", "понятно"
])

# Вопросительные паттерны (если вопрос и нет ключевых слов)
_QUESTION_PATTERNS = re.compile(r'[?؟]|\b(?:когда|зачем|почему|где|что за)\b', re.IGNORECASE)


def parse_task(text: str, known_usernames: list[str]) -> dict:
    text_lower = text.lower()
    at_mentions = re.findall(r'@([a-zA-Z0-9_]+)', text)
    assignees = [m for m in at_mentions if m.lower() in [u.lower() for u in known_usernames]]
    deadline = date_utils.parse_deadline(text)
    task = text.strip()
    for assignee in assignees:
        task = re.sub(rf'@?{re.escape(assignee)}\b', '', task, flags=re.IGNORECASE)
    if deadline:
        task = re.sub(re.escape(deadline), '', task, flags=re.IGNORECASE)
    task = re.sub(r'\s+', ' ', task).strip(' ,.-:')
    if not task:
        task = text.strip()

    has_keyword = any(re.search(rf'\b{kw}\b', text_lower) for kw in _TASK_KEYWORDS)
    has_stopword = any(re.search(rf'\b{sw}\b', text_lower) for sw in _STOP_WORDS)
    has_question = _QUESTION_PATTERNS.search(text_lower) is not None
    has_deadline = deadline is not None
    has_assignee = len(assignees) > 0
    task_length = len(task)
    word_count = len(text_lower.split())

    # Если есть стоп-слово – точно не задача
    if has_stopword:
        confidence = 0
    # Если сообщение очень короткое и нет ключевых слов, дедлайна, ответственных
    elif word_count <= 3 and not has_keyword and not has_deadline and not has_assignee:
        confidence = 0
    # Если это вопрос и нет ключевых слов (например, «Это шаблон?»)
    elif has_question and not has_keyword and not has_deadline and not has_assignee:
        confidence = 0
    elif not has_keyword and not has_deadline and not has_assignee:
        confidence = 0
    else:
        if has_assignee and not has_deadline and not has_keyword:
            confidence = 60
        else:
            if task_length > 5 and has_deadline and has_assignee:
                confidence = 90
            elif task_length > 5 and (has_deadline or has_assignee):
                confidence = 75
            elif task_length > 5:
                confidence = 55
            else:
                confidence = 30

    return {
        "task": task,
        "deadline": deadline,
        "assignees": assignees,
        "confidence": confidence,
    }