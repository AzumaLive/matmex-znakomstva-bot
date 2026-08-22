import os

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_ENV_PATH):
    with open(_ENV_PATH, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _key, _, _value = _line.partition("=")
            os.environ.setdefault(_key.strip(), _value.strip())

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

TIMEZONE = "Asia/Yekaterinburg"

PAIR_START_HOUR = 0
PAIR_START_MINUTE = 0

ADMIN_IDS = [
    990527370,
    1444691093,
]

TOPICS = [
    "Тема 1",
    "Тема 2",
    "Тема 3",
]
