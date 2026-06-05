import re
from typing import Optional
from . import date_utils

# Ключевые слова, указывающие на наличие задачи
_TASK_KEYWORDS = frozenset([
    "сделать", "задача", "нужно", "дедлайн",
    "до", "к", "выполнить", "подготовить", "проверить",
])


def parse_task(
    text: str,
    known_usernames: list[str],
) -> dict[str, Optional[str | int]]:
    """
    Парсит сообщение: извлекает задачу, дедлайн, ответственного и confidence-скор.

    Returns:
        dict с ключами: task, deadline, assignee, confidence.
    """
    text_lower = text.lower()
    known_lower = [u.lower() for u in known_usernames]

    # 1. Ответственный: сначала @упоминания, затем совпадение с known_usernames
    assignee: Optional[str] = None
    for mention in re.findall(r'@([a-zA-Z0-9_]+)', text):
        if mention.lower() in known_lower:
            assignee = mention
            break
    if not assignee:
        for username in known_usernames:
            if re.search(rf'\b{re.escape(username)}\b', text_lower):
                assignee = username
                break

    # 2. Дедлайн
    deadline: Optional[str] = date_utils.parse_deadline(text)

    # 3. Текст задачи: исходный текст минус найденные метаданные
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

    return {
        "task": task,
        "deadline": deadline,
        "assignee": assignee,
        "confidence": confidence,
    }


def _calculate_confidence(
    task: str,
    deadline: Optional[str],
    assignee: Optional[str],
    text_lower: str,
) -> int:
    has_task = len(task) > 5
    has_deadline = deadline is not None
    has_assignee = assignee is not None
    has_keyword = any(re.search(rf'\b{kw}\b', text_lower) for kw in _TASK_KEYWORDS)
    
    # Без ключевого слова задача считается только если есть дедлайн или ответственный
    if not has_keyword:
        if has_deadline or has_assignee:
            return 60   # допустимо, но не высоко
        else:
            return 0    # иначе это не задача
    
    # Если ключевое слово есть:
    if has_task and has_deadline and has_assignee:
        return 90
    if has_task and (has_deadline or has_assignee):
        return 75
    if has_task:
        return 55       # чуть выше будущего порога
    return 30
