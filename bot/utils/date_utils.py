import re
import dateparser
from datetime import datetime, timezone
from typing import Optional

# Все возможные формы дней недели
days = r'(понедельник|понедельника|понедельнику|понедельник|понедельником|понедельнике|' \
       r'вторник|вторника|вторнику|вторник|вторником|вторнике|' \
       r'среда|среды|среде|среду|средой|среде|' \
       r'четверг|четверга|четвергу|четверг|четвергом|четверге|' \
       r'пятница|пятницы|пятнице|пятницу|пятницей|пятнице|' \
       r'суббота|субботы|субботе|субботу|субботой|субботе|' \
       r'воскресенье|воскресенья|воскресенью|воскресенье|воскресеньем|воскресенье)'

def parse_deadline(text: str) -> Optional[str]:
    text_lower = text.lower()
    patterns = [
        r'(до|к)\s+\d{1,2}:\d{2}',
        r'(до|к)\s+\d{1,2}[\.\/\-]\d{1,2}',
        r'(до|к)\s+\d{1,2}[\.\/\-]\d{1,2}[\.\/\-]\d{2,4}',
        rf'(до|к)\s+{days}',
        r'\bзавтра\b',
        r'\bпослезавтра\b',
        r'через\s+\d+\s+(дня|дней|часов|час|неделю|недели|месяц|месяца)',
        rf'\b{days}\b'
    ]
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            return match.group(0)
    return None

def deadline_to_timestamp(deadline_str: str, reference_date: Optional[datetime] = None) -> Optional[int]:
    if not deadline_str:
        return None
    default_time = "23:59:59"
    settings = {
        'PREFER_DATES_FROM': 'future',
        'RELATIVE_BASE': reference_date or datetime.now(timezone.utc),
        'TIMEZONE': 'Europe/Moscow',
    }
    parsed = dateparser.parse(deadline_str, settings=settings)
    if parsed is None and not re.search(r'\d{1,2}:\d{2}', deadline_str):
        parsed = dateparser.parse(deadline_str + " " + default_time, settings=settings)
    return int(parsed.timestamp() * 1000) if parsed else None