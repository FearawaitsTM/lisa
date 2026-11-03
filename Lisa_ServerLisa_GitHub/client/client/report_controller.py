import threading
import os
from pathlib import Path
from tkinter import filedialog, messagebox


class ReportController:
    def __init__(self, app):
        self.app = app
        self.selected_file_path = None
        self.all_summaries = []

    def choose_local_file(self):
        self.selected_file_path = filedialog.askopenfilename(
            title="Выбери отчёт Sigur",
            filetypes=[("Отчёты Sigur", "*.xlsx *.csv"), ("Все файлы", "*.*")],
        )
        if self.selected_file_path:
            self.app.selected_file_var.set(self.selected_file_path.split("/")[-1])

    def process_local_file(self):
        if not self.selected_file_path:
            messagebox.showwarning("Файл не выбран", "Сначала выбери файл")
            return
        self.app.local_report_button.config(state="disabled")
        self.app.status_var.set("Обработка локального отчёта...")
        selected_file_path = self.selected_file_path

        def worker():
            try:
                from .process_sigur_report import generate_daily_report

                report_data = generate_daily_report(
                    selected_file_path,
                    night_employees=self.app.night_employees,
                )
                self.app.root.after(0, lambda: self.show_report(report_data, "Локальный файл"))
            except Exception as error:
                error_text = str(error)
                self.app.root.after(0, lambda: messagebox.showerror("Ошибка", error_text))
                self.app.root.after(0, lambda: self.app.status_var.set("Ошибка обработки отчёта"))
            finally:
                self.app.root.after(0, lambda: self.app.local_report_button.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def request_server_report(self):
        self.app.server_button.config(state="disabled")
        self.app.status_var.set("Формирование отчёта...")
        server_url = self.app.server_entry.get().strip()
        date_from = self.app.date_from_entry.get().strip()
        date_to = self.app.date_to_entry.get().strip()
        try:
            self.app.api_client.update_server_url(server_url)
            self.app.save_current_settings()
        except Exception as error:
            self.app.server_button.config(state="normal")
            self.app.status_var.set("Неверный адрес сервера")
            messagebox.showerror("Ошибка", str(error))
            return

        def worker():
            saved_report_path = None
            try:
                from .process_sigur_report import generate_daily_report

                content = self.app.api_client.get_report_file(date_from, date_to)
                report_extension = ".xlsx" if content.startswith(b"PK") else ".csv"
                report_folder = Path(
                    os.getenv("LOCALAPPDATA") or Path.home()
                ) / "Lisa"
                report_folder.mkdir(parents=True, exist_ok=True)
                saved_report_path = report_folder / f"last_server_report{report_extension}"
                saved_report_path.write_bytes(content)
                report_data = generate_daily_report(
                    content,
                    night_employees=self.app.night_employees,
                )
                self.app.root.after(0, lambda: self.show_report(report_data, "Отчёт с сервера"))
            except Exception as error:
                error_text = str(error)
                if saved_report_path is not None:
                    error_text += f"\n\nПолученный файл сохранён:\n{saved_report_path}"
                self.app.root.after(0, lambda: messagebox.showerror("Ошибка", error_text))
                self.app.root.after(0, lambda: self.app.status_var.set("Ошибка получения отчёта"))
            finally:
                self.app.root.after(0, lambda: self.app.server_button.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def show_report(self, report_data, source_name):
        self.all_summaries = report_data.get("summaries", [])
        self.app.filter_var.set("")
        self.app.apply_filter()
        events_count = len(report_data.get("events", []))
        self.app.status_var.set(
            f"{source_name}: событий {events_count}, строк {len(self.all_summaries)}"
        )
