import json
from datetime import datetime

from .settings import APP_DIR, DEFAULT_SETTINGS, SETTINGS_FILE


def normalize_server_url(value):
    value = str(value).strip().rstrip("/")
    if not value:
        raise ValueError("Укажи адрес сервера")
    if not value.startswith(("http://", "https://")):
        value = "http://" + value
    return value


def validate_date(value):
    datetime.strptime(value, "%Y-%m-%d")


def load_settings():
    if not SETTINGS_FILE.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_SETTINGS)
    settings = dict(DEFAULT_SETTINGS)
    settings.update(data)
    return settings


def save_settings(settings):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def version_tuple(value):
    parts = []
    for part in str(value).strip().split("."):
        digits = "".join(symbol for symbol in part if symbol.isdigit())
        parts.append(int(digits or 0))
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def is_newer_version(server_version, current_version):
    return version_tuple(server_version) > version_tuple(current_version)
