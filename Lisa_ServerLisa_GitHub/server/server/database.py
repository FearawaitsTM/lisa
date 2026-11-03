import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

try:
    import psycopg
except Exception:
    psycopg = None

from .config import DATABASE_URL


def is_postgres():
    return DATABASE_URL.startswith(("postgres://", "postgresql://"))


def sqlite_path():
    return Path(DATABASE_URL.replace("sqlite:///", "", 1))


@contextmanager
def get_connection():
    if is_postgres():
        if psycopg is None:
            raise RuntimeError("Для PostgreSQL установи пакет psycopg[binary]")
        connection = psycopg.connect(DATABASE_URL)
    else:
        path = sqlite_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=10)
        connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize_database():
    if is_postgres():
        sql = """
        CREATE TABLE IF NOT EXISTS night_employee_periods (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            tab_number TEXT NOT NULL DEFAULT '',
            shift_type TEXT NOT NULL DEFAULT 'night',
            start_time TEXT NOT NULL DEFAULT '19:00',
            end_time TEXT NOT NULL DEFAULT '08:00',
            valid_from DATE NOT NULL,
            valid_to DATE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (name, tab_number, valid_from)
        );
        """
    else:
        sql = """
        CREATE TABLE IF NOT EXISTS night_employee_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            tab_number TEXT NOT NULL DEFAULT '',
            shift_type TEXT NOT NULL DEFAULT 'night',
            start_time TEXT NOT NULL DEFAULT '19:00',
            end_time TEXT NOT NULL DEFAULT '08:00',
            valid_from TEXT NOT NULL,
            valid_to TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (name, tab_number, valid_from)
        );
        """

    with get_connection() as connection:
        if not is_postgres():
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute(sql)
        _ensure_schedule_columns(connection)
        migrate_old_night_employees(connection)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_shift_periods_dates "
            "ON night_employee_periods(valid_from, valid_to)"
        )


def _ensure_schedule_columns(connection):
    if is_postgres():
        statements = (
            "ALTER TABLE night_employee_periods ADD COLUMN IF NOT EXISTS shift_type TEXT NOT NULL DEFAULT 'night'",
            "ALTER TABLE night_employee_periods ADD COLUMN IF NOT EXISTS start_time TEXT NOT NULL DEFAULT '19:00'",
            "ALTER TABLE night_employee_periods ADD COLUMN IF NOT EXISTS end_time TEXT NOT NULL DEFAULT '08:00'",
        )
        for statement in statements:
            connection.execute(statement)
        return

    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(night_employee_periods)").fetchall()
    }
    additions = {
        "shift_type": "TEXT NOT NULL DEFAULT 'night'",
        "start_time": "TEXT NOT NULL DEFAULT '19:00'",
        "end_time": "TEXT NOT NULL DEFAULT '08:00'",
    }
    for column, definition in additions.items():
        if column not in columns:
            connection.execute(
                f"ALTER TABLE night_employee_periods ADD COLUMN {column} {definition}"
            )


def migrate_old_night_employees(connection):
    try:
        if is_postgres():
            rows = connection.execute("SELECT name, tab_number FROM night_employees").fetchall()
        else:
            old_table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='night_employees'"
            ).fetchone()
            if not old_table:
                return
            rows = connection.execute("SELECT name, tab_number FROM night_employees").fetchall()

        for row in rows:
            item = row_to_dict(row, columns=("name", "tab_number"))
            values = (
                item["name"],
                item.get("tab_number", ""),
                "night",
                "19:00",
                "08:00",
                "2000-01-01",
                None,
            )
            if is_postgres():
                connection.execute(
                    """
                    INSERT INTO night_employee_periods
                    (name, tab_number, shift_type, start_time, end_time, valid_from, valid_to)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (name, tab_number, valid_from) DO NOTHING
                    """,
                    values,
                )
            else:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO night_employee_periods
                    (name, tab_number, shift_type, start_time, end_time, valid_from, valid_to)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
    except Exception:
        # Старой таблицы может не быть; это штатная ситуация на новой установке.
        pass


def row_to_dict(row, columns=None):
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    try:
        return dict(row)
    except Exception:
        columns = columns or (
            "id",
            "name",
            "tab_number",
            "shift_type",
            "start_time",
            "end_time",
            "valid_from",
            "valid_to",
            "created_at",
        )
        return {column: row[index] for index, column in enumerate(columns)}


def _validate_date(value, field_name, required=True):
    value = str(value or "").strip() or None
    if value is None:
        if required:
            raise ValueError(f"Укажи дату «{field_name}»")
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError(f"Дата «{field_name}» должна быть YYYY-MM-DD") from error
    return value


def _validate_time(value, field_name):
    value = str(value or "").strip()
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError as error:
        raise ValueError(f"Время «{field_name}» должно быть HH:MM") from error
    return value


def _normalize_shift_type(value):
    value = str(value or "").strip().lower()
    if value not in {"day", "night"}:
        raise ValueError("Тип смены должен быть day или night")
    return value


def list_shift_schedules():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, name, tab_number, shift_type, start_time, end_time,
                   valid_from, valid_to, created_at
            FROM night_employee_periods
            ORDER BY name, valid_from, start_time
            """
        ).fetchall()

    result = []
    for row in rows:
        item = row_to_dict(row)
        for key in ("valid_from", "valid_to"):
            value = item.get(key)
            if hasattr(value, "strftime"):
                item[key] = value.strftime("%Y-%m-%d")
        created_at = item.get("created_at")
        if hasattr(created_at, "strftime"):
            item["created_at"] = created_at.strftime("%Y-%m-%d %H:%M:%S")
        result.append(item)
    return result


def add_shift_schedule(
    name,
    tab_number="",
    shift_type="day",
    start_time="08:00",
    end_time="20:00",
    valid_from=None,
    valid_to=None,
):
    name = " ".join(str(name or "").split())
    tab_number = str(tab_number or "").strip()
    if not name:
        raise ValueError("Укажи ФИО сотрудника")

    shift_type = _normalize_shift_type(shift_type)
    start_time = _validate_time(start_time, "начало смены")
    end_time = _validate_time(end_time, "конец смены")
    valid_from = _validate_date(valid_from, "с")
    valid_to = _validate_date(valid_to, "по", required=False)
    if valid_to and valid_to < valid_from:
        raise ValueError("Дата «по» не может быть раньше даты «с»")

    values = (
        name,
        tab_number,
        shift_type,
        start_time,
        end_time,
        valid_from,
        valid_to,
    )
    with get_connection() as connection:
        if is_postgres():
            row = connection.execute(
                """
                INSERT INTO night_employee_periods
                (name, tab_number, shift_type, start_time, end_time, valid_from, valid_to)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (name, tab_number, valid_from)
                DO UPDATE SET shift_type=EXCLUDED.shift_type,
                              start_time=EXCLUDED.start_time,
                              end_time=EXCLUDED.end_time,
                              valid_to=EXCLUDED.valid_to
                RETURNING id, name, tab_number, shift_type, start_time, end_time,
                          valid_from, valid_to, created_at
                """,
                values,
            ).fetchone()
            return row_to_dict(row)

        connection.execute(
            """
            INSERT INTO night_employee_periods
            (name, tab_number, shift_type, start_time, end_time, valid_from, valid_to)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name, tab_number, valid_from)
            DO UPDATE SET shift_type=excluded.shift_type,
                          start_time=excluded.start_time,
                          end_time=excluded.end_time,
                          valid_to=excluded.valid_to
            """,
            values,
        )
        row = connection.execute(
            """
            SELECT id, name, tab_number, shift_type, start_time, end_time,
                   valid_from, valid_to, created_at
            FROM night_employee_periods
            WHERE name=? AND tab_number=? AND valid_from=?
            """,
            (name, tab_number, valid_from),
        ).fetchone()
        return row_to_dict(row)


def delete_shift_schedule(schedule_id):
    with get_connection() as connection:
        if is_postgres():
            connection.execute(
                "DELETE FROM night_employee_periods WHERE id=%s", (schedule_id,)
            )
        else:
            connection.execute(
                "DELETE FROM night_employee_periods WHERE id=?", (schedule_id,)
            )
    return {"ok": True}


# Старые клиенты продолжают работать через прежние имена и маршруты.
list_night_employees = list_shift_schedules
add_night_employee = add_shift_schedule
delete_night_employee = delete_shift_schedule
