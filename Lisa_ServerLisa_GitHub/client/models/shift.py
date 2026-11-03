from dataclasses import dataclass


@dataclass(frozen=True)
class ShiftRules:
    employee_type: str
    starts_previous_evening: bool = False
