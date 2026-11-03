import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from tkinter import messagebox

import requests

from .constants import CURRENT_VERSION, UPDATE_CHECK_INTERVAL_MS, UPDATER_FILE_NAME
from .utils import is_newer_version


class UpdateManager:
    def __init__(self, app):
        self.app = app
        self.available_update = None
        self._checking = False
        self._update_in_progress = False

    def start_automatic_checks(self):
        self.check_for_updates(silent=True, auto_install=True)
        self.app.root.after(UPDATE_CHECK_INTERVAL_MS, self.start_automatic_checks)

    def get_program_path(self):
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve()
        return Path(__file__).resolve()

    def get_program_folder(self):
        return self.get_program_path().parent

    def calculate_sha256(self, file_path):
        digest = hashlib.sha256()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest().lower()

    def check_for_updates(self, silent=False, auto_install=False):
        if self._checking or self._update_in_progress:
            return
        try:
            self.app.api_client.update_server_url(self.app.server_entry.get().strip())
            self.app.save_current_settings()
        except Exception as error:
            if not silent:
                messagebox.showerror("Ошибка проверки обновлений", str(error))
            return
        self._checking = True

        def worker():
            try:
                manifest = self.app.api_client.get_update_manifest()
                server_version = str(manifest.get("version", "")).strip()
                download_url = str(manifest.get("download_url", "")).strip()
                if not server_version:
                    raise RuntimeError("В version.json не указана version")
                if not download_url:
                    raise RuntimeError("В version.json не указан download_url")
                if is_newer_version(server_version, CURRENT_VERSION):
                    self.app.root.after(
                        0,
                        lambda: self._handle_available_update(manifest, auto_install),
                    )
                elif not silent:
                    self.app.root.after(
                        0,
                        lambda: messagebox.showinfo(
                            "Обновление",
                            f"Установлена последняя версия: {CURRENT_VERSION}",
                        ),
                    )
            except json.JSONDecodeError as error:
                if not silent:
                    error_text = str(error)
                    self.app.root.after(0, lambda: messagebox.showerror("Ошибка проверки обновлений", error_text))
            except Exception as error:
                if not silent:
                    error_text = str(error)
                    self.app.root.after(0, lambda: messagebox.showerror("Ошибка проверки обновлений", error_text))
            finally:
                self._checking = False

        threading.Thread(target=worker, daemon=True).start()

    def _handle_available_update(self, manifest, auto_install):
        self.app.show_update_banner(manifest)
        if auto_install:
            self.app.root.after(250, lambda: self.start_update(silent=True))

    def start_update(self, silent=False):
        if self._update_in_progress:
            return
        manifest = self.available_update
        if not manifest:
            if not silent:
                messagebox.showwarning("Обновление", "Информация об обновлении не загружена")
            return
        if not getattr(sys, "frozen", False):
            if not silent:
                messagebox.showwarning("Обновление", "Автообновление работает только в собранном EXE-файле.")
            return

        updater_path = self.get_program_folder() / UPDATER_FILE_NAME
        if not updater_path.exists():
            self.app.update_details_var.set(
                f"Для автоматического обновления положи {UPDATER_FILE_NAME} рядом с программой"
            )
            if not silent:
                messagebox.showerror("Ошибка обновления", f"Рядом с программой не найден {UPDATER_FILE_NAME}")
            return

        download_url = manifest["download_url"]
        expected_sha256 = str(manifest.get("sha256", "")).strip().lower()
        new_version = str(manifest.get("version", "")).strip()
        self._update_in_progress = True
        self.app.update_button.config(state="disabled", text="Скачивание...")
        self.app.update_details_var.set("Загружается новая версия...")

        def worker():
            try:
                update_folder = Path(tempfile.gettempdir()) / "lisa_client_update"
                update_folder.mkdir(parents=True, exist_ok=True)
                downloaded_file = update_folder / f"Лиса_{new_version}.exe"
                with requests.get(download_url, stream=True, timeout=(15, 300), headers={"Cache-Control": "no-cache"}) as response:
                    response.raise_for_status()
                    with open(downloaded_file, "wb") as file:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                file.write(chunk)
                if not downloaded_file.exists() or downloaded_file.stat().st_size == 0:
                    raise RuntimeError("Сервер прислал пустой файл")
                if expected_sha256 and self.calculate_sha256(downloaded_file) != expected_sha256:
                    downloaded_file.unlink(missing_ok=True)
                    raise RuntimeError("Контрольная сумма обновления не совпала")
                current_program = self.get_program_path()
                subprocess.Popen(
                    [
                        str(updater_path),
                        "--pid",
                        str(os.getpid()),
                        "--source",
                        str(downloaded_file),
                        "--target",
                        str(current_program),
                        "--restart",
                        str(current_program),
                    ],
                    cwd=str(self.get_program_folder()),
                    close_fds=True,
                )
                self.app.root.after(0, self.app.root.destroy)
            except Exception as error:
                self._update_in_progress = False
                error_text = str(error)
                if not silent:
                    self.app.root.after(0, lambda: messagebox.showerror("Ошибка обновления", error_text))
                self.app.root.after(0, lambda: self.app.update_button.config(state="normal", text="Обновить"))
                self.app.root.after(
                    0,
                    lambda: self.app.update_details_var.set(
                        f"Не удалось установить обновление: {error_text}"
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()
