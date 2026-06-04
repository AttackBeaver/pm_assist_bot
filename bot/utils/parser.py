import re
from typing import Dict, Optional, List
from . import date_utils


def parse_task(text: str, known_usernames: List[str]) -> Dict[str, Optional[str | int]]:
    """
    Парсит сообщение на наличие задачи, дедлайна и ответственного.
    """
    text_lower = text.lower()

    # 1. Поиск ответственного (assignee)
    assignee = None
    known_usernames_lower = [u.lower() for u in known_usernames]

    # Сначала ищем явные упоминания через @
    at_mentions = re.findall(r'@([a-zA-Z0-9_]+)', text)
    for mention in at_mentions:
        if mention.lower() in known_usernames_lower:
            assignee = mention
            break

    # Если @ нет, ищем совпадения с known_usernames как целые слова
    if not assignee:
        for username in known_usernames:
            # \b гарантирует границу слова, чтобы "ivan" не матчился внутри "ivanov"
            if re.search(rf'\b{re.escape(username)}\b', text_lower):
                assignee = username
                break

    # 2. Поиск дедлайна (deadline)
    deadline = date_utils.parse_deadline(text)

    # 3. Формирование текста задачи (task)
    # Эвристика: берем исходный текст и удаляем из него найденные метаданные
    task = text.strip()

    if assignee:
        # Удаляем @username или просто username (с учетом регистра)
        task = re.sub(rf'@?{re.escape(assignee)}\b',
                      '', task, flags=re.IGNORECASE)

    if deadline:
        # Удаляем найденную фразу дедлайна из текста задачи
        task = re.sub(re.escape(deadline), '', task, flags=re.IGNORECASE)

    # Очистка от лишних пробелов, знаков препинания в начале/конце
    task = re.sub(r'\s+', ' ', task).strip(' ,.-:')

    # Если после очистки текст пуст, возвращаем исходный (значит, метаданных не было)
    if not task:
        task = text.strip()

    # 4. Расчет доверительного скора (confidence)
    confidence = calculate_confidence(
        {"task": task, "deadline": deadline, "assignee": assignee}, text)

    return {
        "task": task,
        "deadline": deadline,
        "assignee": assignee,
        "confidence": confidence
    }


def calculate_confidence(parse_result: Dict[str, Optional[str]], original_text: str) -> int:
    """
    Оценивает вероятность того, что сообщение является реальной задачей (0–100).
    """
    has_task = bool(parse_result.get("task") and len(parse_result["task"]) > 5)
    has_deadline = bool(parse_result.get("deadline"))
    has_assignee = bool(parse_result.get("assignee"))

    # Проверка на наличие ключевых слов задачи
    keywords = ["сделать", "задача", "нужно", "дедлайн",
                "до", "к", "выполнить", "подготовить", "проверить"]
    has_keyword = any(
        re.search(rf'\b{kw}\b', original_text.lower()) for kw in keywords)

    if not has_keyword and not has_task:
        return 0

    if has_task and has_deadline and has_assignee:
        return 90
    elif has_task and (has_deadline or has_assignee):
        return 70
    elif has_task:
        return 50

    # Низкая уверенность (есть ключевые слова, но задача не выделена четко)
    return 30
