from datetime import time

DEFAULT_SERVER_URL = "http://192.168.10.75"
LEGACY_SERVER_URLS = {
    "http://192.168.0.199:8000",
}
CURRENT_VERSION = "4.1.14"
UPDATE_MANIFEST_PATH = "/updates/version.json"
UPDATER_FILE_NAME = "Updater.exe"
UPDATE_CHECK_INTERVAL_MS = 15 * 60 * 1000

EARLY_ARRIVAL_LIMIT = time(7, 30)
LATE_LIMIT = time(9, 15)
EARLY_LEAVE_LIMIT = time(16, 0)
NIGHT_SHIFT_NOON_LIMIT = time(12, 0)

TABLE_COLUMNS = [
    ("report_date", "Дата", 100),
    ("tab_number", "Табельный номер", 115),
    ("employee_name", "ФИО", 250),
    ("employee_type", "Смена", 95),
    ("first_in_time", "Первый вход", 100),
    ("last_out_time", "Последний выход", 115),
    ("worked_time", "Отработано", 110),
    ("break_count", "Выходов", 80),
    ("total_break_time", "Время выходов", 120),
    ("selected_total", "Выбрано", 110),
    ("first_in_reader", "Считыватель входа", 180),
    ("last_out_reader", "Считыватель выхода", 180),
    ("arrival_status", "Приход", 120),
    ("departure_status", "Уход", 120),
    ("presence_status", "Присутствие", 125),
]
