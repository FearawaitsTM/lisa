import threading
from tkinter import messagebox

from .utils import validate_date


class EmployeeController:
    def __init__(self, app):
        self.app = app

    def refresh_night_employees(self):
        self.app.night_status_var.set("Загрузка списка...")

        def worker():
            try:
                employees = self.app.api_client.list_night_employees()
                self.app.root.after(0, lambda: self.apply_night_employees(employees))
            except Exception as error:
                error_text = str(error)
                self.app.root.after(0, lambda: self.app.night_status_var.set("Не удалось загрузить список"))
                self.app.root.after(0, lambda: messagebox.showerror("Ночники", error_text))

        threading.Thread(target=worker, daemon=True).start()

    def apply_night_employees(self, employees):
        self.app.night_employees_raw = employees
        self.app.night_employees = employees
        self.app.populate_night_table()
        self.app.apply_filter()
        self.app.night_status_var.set(f"Периодов ночников: {len(employees)}")

    def add_night_employee(self):
        name = self.app.night_name_var.get().strip()
        tab_number = self.app.night_tab_var.get().strip()
        valid_from = self.app.night_from_var.get().strip()
        valid_to = self.app.night_to_var.get().strip()
        if not name:
            messagebox.showwarning("Ночники", "Укажи ФИО сотрудника")
            return
        try:
            validate_date(valid_from)
            if valid_to:
                validate_date(valid_to)
            if valid_to and valid_to < valid_from:
                raise ValueError("Дата 'по' не может быть раньше даты 'с'")
        except Exception as error:
            messagebox.showwarning("Ночники", str(error))
            return
        self.app.night_add_button.config(state="disabled")

        def worker():
            try:
                self.app.api_client.add_night_employee(name, tab_number, valid_from, valid_to)
                employees = self.app.api_client.list_night_employees()
                self.app.root.after(0, lambda: self.app.night_name_var.set(""))
                self.app.root.after(0, lambda: self.app.night_tab_var.set(""))
                self.app.root.after(0, lambda: self.app.night_to_var.set(""))
                self.app.root.after(0, lambda: self.apply_night_employees(employees))
            except Exception as error:
                error_text = str(error)
                self.app.root.after(0, lambda: messagebox.showerror("Ночники", error_text))
            finally:
                self.app.root.after(0, lambda: self.app.night_add_button.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def delete_selected_night_employee(self):
        selected_rows = self.app.night_sheet.get_selected_rows(get_cells_as_rows=True)
        selected_cells = self.app.night_sheet.get_selected_cells()
        rows_from_cells = {row_index for row_index, _ in selected_cells}
        rows = sorted(set(selected_rows) | rows_from_cells)
        if not rows:
            messagebox.showwarning("Ночники", "Выбери строку для удаления")
            return
        row_index = rows[0]
        if row_index >= len(self.app.night_employees_raw):
            return
        employee_id = self.app.night_employees_raw[row_index]["id"]

        def worker():
            try:
                self.app.api_client.delete_night_employee(employee_id)
                employees = self.app.api_client.list_night_employees()
                self.app.root.after(0, lambda: self.apply_night_employees(employees))
            except Exception as error:
                error_text = str(error)
                self.app.root.after(0, lambda: messagebox.showerror("Ночники", error_text))

        threading.Thread(target=worker, daemon=True).start()
