import ctypes
import os
import tkinter as tk
from tkinter import messagebox

from logic.filters import filter_summaries
from logic.highlights import build_highlights
from logic.totals import calculate_selected_totals

from .api_client import ApiClient
from .constants import DEFAULT_SERVER_URL, LEGACY_SERVER_URLS, TABLE_COLUMNS
from .employee_controller import EmployeeController
from .report_controller import ReportController
from .resource import resource_path
from .ui import build_ui, place_update_banner
from .update_manager import UpdateManager
from .utils import load_settings, save_settings


class LisaApp:
    def __init__(self):
        if os.name == "nt":
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "Aristocrat.Lisa.Client"
                )
            except Exception:
                pass

        self.root = tk.Tk()
        try:
            self.root.iconbitmap(resource_path("1.ico"))
        except tk.TclError:
            pass

        self.settings = load_settings()
        saved_server_url = str(self.settings.get("server_url", "")).strip().rstrip("/")
        if saved_server_url in LEGACY_SERVER_URLS:
            self.settings["server_url"] = DEFAULT_SERVER_URL
            save_settings(self.settings)
        self.api_client = ApiClient(self.settings["server_url"])
        self.night_employees_raw = []
        self.night_employees = set()
        self.filtered_summaries = []
        self._filter_after_id = None
        self._table_columns = [key for key, _, _ in TABLE_COLUMNS]

        self.update_manager = UpdateManager(self)
        self.report_controller = ReportController(self)
        self.employee_controller = EmployeeController(self)
        build_ui(self)

    def run(self):
        self.root.after(500, self.employee_controller.refresh_night_employees)
        self.root.after(1000, self.update_manager.start_automatic_checks)
        self.root.mainloop()

    def save_current_settings(self):
        server_url = self.api_client.server_url
        if self.settings.get("server_url") == server_url:
            return
        self.settings["server_url"] = server_url
        save_settings(self.settings)

    def hide_update_banner(self):
        self.update_frame.place_forget()

    def show_update_banner(self, manifest):
        self.update_manager.available_update = manifest
        place_update_banner(self, manifest)

    def populate_night_table(self):
        rows = [
            [
                employee.get("id", ""),
                employee.get("name", ""),
                employee.get("tab_number", ""),
                employee.get("valid_from", ""),
                employee.get("valid_to", "") or "по настоящее время",
                employee.get("created_at", ""),
            ]
            for employee in self.night_employees_raw
        ]
        self.night_sheet.set_sheet_data(rows, reset_highlights=True, delete_options=True)
        self.night_sheet.headers(["ID", "ФИО", "Табельный номер", "Ночник с", "Ночник по", "Добавлен"])
        self.night_sheet.column_width(column=0, width=70, redraw=False)
        self.night_sheet.column_width(column=1, width=360, redraw=False)
        self.night_sheet.column_width(column=2, width=150, redraw=False)
        self.night_sheet.column_width(column=3, width=120, redraw=False)
        self.night_sheet.column_width(column=4, width=150, redraw=False)
        self.night_sheet.column_width(column=5, width=180, redraw=False)
        self.night_sheet.redraw()

    def schedule_filter(self, *_):
        if self._filter_after_id is not None:
            self.root.after_cancel(self._filter_after_id)
        self._filter_after_id = self.root.after(120, self.apply_filter)

    def apply_filter(self, *_):
        if self._filter_after_id is not None:
            try:
                self.root.after_cancel(self._filter_after_id)
            except tk.TclError:
                pass
            self._filter_after_id = None
        summaries = self.report_controller.all_summaries
        self.filtered_summaries = filter_summaries(
            summaries,
            self.filter_var.get(),
            self.employee_type_var.get(),
        )
        self.populate_table(self.filtered_summaries)
        self.count_var.set(f"Строк: {len(self.filtered_summaries)}")

    def populate_table(self, summaries):
        table_data = []
        for summary in summaries:
            row_values = [summary.get(key, "") for key in self._table_columns]
            table_data.append(row_values)

        self.sheet.set_sheet_data(
            table_data,
            reset_highlights=True,
            delete_options=True,
            redraw=False,
        )
        self.sheet.headers([heading for _, heading, _ in TABLE_COLUMNS])
        for column_index, (_, _, width) in enumerate(TABLE_COLUMNS):
            self.sheet.column_width(column=column_index, width=width, redraw=False)
        for row, column, background in build_highlights(summaries, self._table_columns):
            self.sheet.highlight_cells(row=row, column=column, bg=background, fg="black", redraw=False)
        self.sheet.redraw()

    def on_employee_select(self, _event=None):
        selected_cells = self.sheet.get_selected_cells()
        selected_rows = self.sheet.get_selected_rows(get_cells_as_rows=True)
        rows_from_cells = {row_index for row_index, _ in selected_cells}
        all_selected_rows = sorted(set(selected_rows) | rows_from_cells)
        if not all_selected_rows:
            return

        selected_rows_data = []
        employee_names = set()
        full_rows = []
        for row_index in all_selected_rows:
            row_data = self.sheet.get_row_data(row_index)
            if not row_data:
                continue
            employee_names.add(row_data[2])
            full_rows.append(row_data)
            selected_rows_data.append([
                row_data[0],
                row_data[3],
                row_data[4],
                row_data[5],
                row_data[6],
                row_data[7],
                row_data[8],
            ])

        self.employee_sheet.set_sheet_data(selected_rows_data, redraw=False)
        self.employee_sheet.redraw()

        totals = calculate_selected_totals(
            full_rows,
            worked_index=6,
            break_count_index=7,
            break_time_index=8,
        )

        if len(employee_names) == 1:
            self.selected_employee_var.set(next(iter(employee_names)))
        else:
            self.selected_employee_var.set(f"Выбрано сотрудников: {len(employee_names)}")

        self.total_worked_var.set(f"Всего по выбранным строкам: {totals['worked_time']}")
        self.total_breaks_var.set(
            f"Выходов: {totals['break_count']}, время выходов: {totals['break_time']}"
        )

    def show_error(self, title, error):
        messagebox.showerror(title, str(error))
