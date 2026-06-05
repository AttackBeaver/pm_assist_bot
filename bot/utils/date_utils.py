import re
import dateparser
from datetime import datetime, timezone
from typing import Optional

# Падежные формы дней недели с предлогами "до", "к"
_DAYS_PREPOSITIONAL = (
    r'(?:'
    r'понедельник[уа]?|понедельником|'
    r'вторник[уа]?|вторником|'
    r'сред[уе]|средой|'
    r'четверг[уа]?|четвергом|'
    r'пятниц[уе]|пятницей|'
    r'суббот[уе]|субботой|'
    r'воскресень[ею]|воскресеньем'
    r')'
)

# Падежи для месяцев
_MONTHS_GENITIVE = r'(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)'

def parse_deadline(text: str) -> Optional[str]:
    text_lower = text.lower()
    patterns = [
        r'(?:до|к)\s+\d{1,2}:\d{2}',                                    # до 18:00
        r'(?:до|к)\s+\d{1,2}[./\-]\d{1,2}(?:[./\-]\d{2,4})?',          # до 15.06, до 15.06.2025
        rf'(?:до|к)\s+{_DAYS_PREPOSITIONAL}',                           # до пятницы, к среде
        rf'до\s+\d{{1,2}}\s+{_MONTHS_GENITIVE}',                       # до 7 июня
        rf'до\s+\d{{1,2}}\s+числа',                                    # до 7 числа
        r'\bзавтра\b',
        r'\bпослезавтра\b',
        r'через\s+\d+\s+(?:дня|дней|часов?|неделю|недели|месяц[а]?)', # через 2 дня
        rf'\b{_DAYS_PREPOSITIONAL}\b',                                 # пятница (без предлога)
        r'(?:в|в конце)\s+(?:январе|феврале|марте|апреле|мае|июне|июле|августе|сентябре|октябре|ноябре|декабре)', # в июле
        r'(?:до|к)\s+концу\s+(?:недели|месяца|года)',
        r'(?:на|в)\s+(?:следующей|этой|будущей|прошлой)\s+неделе',
    ]
    for pat in patterns:
        match = re.search(pat, text_lower)
        if match:
            return match.group(0)
    return None

def deadline_to_timestamp(deadline_str: str, reference_date: Optional[datetime] = None) -> Optional[int]:
    if not deadline_str:
        return None
    settings = {
        "PREFER_DATES_FROM": "future",
        "TIMEZONE": "Europe/Moscow",
        "RETURN_AS_TIMEZONE_AWARE": True,
        "RELATIVE_BASE": reference_date or datetime.now(timezone.utc),
    }
    parsed = dateparser.parse(deadline_str, settings=settings)
    # Если время не указано, ставим конец дня
    if parsed is None and not re.search(r'\d{1,2}:\d{2}', deadline_str):
        parsed = dateparser.parse(f"{deadline_str} 23:59:59", settings=settings)
    return int(parsed.timestamp() * 1000) if parsed else None