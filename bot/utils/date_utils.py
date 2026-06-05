import re
import dateparser
from datetime import datetime, timezone
from typing import Optional

# Падежные формы дней недели (без дублей)
_DAYS = (
    r'(?:'
    r'понедельник[аеуи]?|понедельником|'
    r'вторник[аеу]?|вторником|'
    r'сред[аыеу]|средой|'
    r'четверг[аеу]?|четвергом|'
    r'пятниц[аыеу]|пятницей|'
    r'суббот[аыеу]|субботой|'
    r'воскресень[еяю]|воскресеньем'
    r')'
)

_DEADLINE_PATTERNS = [
    rf'(?:до|к)\s+\d{{1,2}}:\d{{2}}',
    rf'(?:до|к)\s+\d{{1,2}}[./\-]\d{{1,2}}(?:[./\-]\d{{2,4}})?',
    rf'(?:до|к)\s+{_DAYS}',
    r'\bзавтра\b',
    r'\bпослезавтра\b',
    r'через\s+\d+\s+(?:дня|дней|часов?|неделю|недели|месяц[а]?)',
    rf'\b{_DAYS}\b',
]

_DEFAULT_END_OF_DAY = "23:59:59"
_DATEPARSER_SETTINGS = {
    "PREFER_DATES_FROM": "future",
    "TIMEZONE": "Europe/Moscow",
    "RETURN_AS_TIMEZONE_AWARE": True,
}


def parse_deadline(text: str) -> Optional[str]:
    """Ищет упоминание дедлайна в тексте, возвращает найденную подстроку или None."""
    text_lower = text.lower()
    
    # Расширенные паттерны: добавлена поддержка «к концу недели», «на следующей неделе»
    extended_patterns = _DEADLINE_PATTERNS + [
        r'(?:до|к)\s+концу\s+(?:недели|месяца|года)',
        r'(?:на|в)\s+(?:следующей|этой|будущей|прошлой)\s+неделе',
    ]
    
    for pattern in extended_patterns:
        match = re.search(pattern, text_lower)
        if match:
            return match.group(0)
    return None

def deadline_to_timestamp(
    deadline_str: str,
    reference_date: Optional[datetime] = None,
) -> Optional[int]:
    """Конвертирует строку дедлайна в Unix-timestamp в миллисекундах или None."""
    if not deadline_str:
        return None

    settings = {
        **_DATEPARSER_SETTINGS,
        "RELATIVE_BASE": reference_date or datetime.now(timezone.utc),
    }

    parsed = dateparser.parse(deadline_str, settings=settings)
    # Если время не указано явно — ставим конец дня
    if parsed is None and not re.search(r'\d{1,2}:\d{2}', deadline_str):
        parsed = dateparser.parse(f"{deadline_str} {_DEFAULT_END_OF_DAY}", settings=settings)

    return int(parsed.timestamp() * 1000) if parsed else None