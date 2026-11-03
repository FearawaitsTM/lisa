DAY_EMPLOYEE = "дневной"
NIGHT_EMPLOYEE = "ночник"


class NightPeriodIndex:
    def __init__(self, night_employees):
        self.periods = normalize_night_periods(night_employees)
        self.by_key = {}

        for order, period in enumerate(self.periods):
            period["_order"] = order
            for key in {period["key"], period["name_key"]}:
                if key:
                    self.by_key.setdefault(key, []).append(period)

    def find(self, name, tab_number, shift_date):
        key = normalize_employee_key(name, tab_number)
        name_key = normalize_employee_key(name)
        candidates = []
        seen = set()

        for lookup_key in {key, name_key}:
            for period in self.by_key.get(lookup_key, []):
                order = period["_order"]
                if order not in seen:
                    seen.add(order)
                    candidates.append(period)

        candidates.sort(key=lambda period: period["_order"])
        for period in candidates:
            if date_in_period(shift_date, period["valid_from"], period["valid_to"]):
                return period
        return None


def normalize_employee_key(name, tab_number=""):
    name_key = " ".join(str(name or "").lower().split())
    tab_key = str(tab_number or "").strip().lower()
    return tab_key or name_key


def normalize_date_value(value):
    value = str(value or "").strip()
    return value or None


def date_in_period(date_value, valid_from=None, valid_to=None):
    date_value = normalize_date_value(date_value)
    valid_from = normalize_date_value(valid_from)
    valid_to = normalize_date_value(valid_to)

    if not date_value:
        return False
    if valid_from and date_value < valid_from:
        return False
    if valid_to and date_value > valid_to:
        return False
    return True


def normalize_night_periods(night_employees):
    periods = []

    for employee in night_employees or []:
        if isinstance(employee, dict):
            name = employee.get("name", "")
            tab_number = employee.get("tab_number", "")
            valid_from = normalize_date_value(
                employee.get("valid_from")
                or employee.get("date_from")
                or employee.get("from")
            )
            valid_to = normalize_date_value(
                employee.get("valid_to")
                or employee.get("date_to")
                or employee.get("to")
            )
        else:
            name = employee
            tab_number = ""
            valid_from = None
            valid_to = None

        key = normalize_employee_key(name, tab_number)
        name_key = normalize_employee_key(name)
        if not key and not name_key:
            continue

        periods.append(
            {
                "key": key,
                "name_key": name_key,
                "valid_from": valid_from,
                "valid_to": valid_to,
            }
        )

    return periods


def build_night_period_index(night_employees):
    if isinstance(night_employees, NightPeriodIndex):
        return night_employees
    return NightPeriodIndex(night_employees)


def find_night_period(name, tab_number, shift_date, night_employees):
    if isinstance(night_employees, NightPeriodIndex):
        return night_employees.find(name, tab_number, shift_date)

    key = normalize_employee_key(name, tab_number)
    name_key = normalize_employee_key(name)

    for period in normalize_night_periods(night_employees):
        if key not in {period["key"], period["name_key"]} and name_key != period["name_key"]:
            continue
        if date_in_period(shift_date, period["valid_from"], period["valid_to"]):
            return period

    return None


def get_employee_type(summary, night_employees):
    period = find_night_period(
        summary.get("employee_name", ""),
        summary.get("tab_number", ""),
        summary.get("report_date", ""),
        night_employees,
    )
    if period:
        return NIGHT_EMPLOYEE
    return DAY_EMPLOYEE
