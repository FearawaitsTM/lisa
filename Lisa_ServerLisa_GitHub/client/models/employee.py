from dataclasses import dataclass


@dataclass
class Employee:
    name: str
    tab_number: str = ""
    employee_type: str = "дневной"
