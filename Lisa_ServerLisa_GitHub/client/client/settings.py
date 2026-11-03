from pathlib import Path

from .constants import DEFAULT_SERVER_URL

APP_DIR = Path.home() / ".lisa_client"
SETTINGS_FILE = APP_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "server_url": DEFAULT_SERVER_URL,
}
