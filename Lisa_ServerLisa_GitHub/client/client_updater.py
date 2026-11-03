import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from tkinter import Tk, messagebox

WAIT_TIMEOUT_SECONDS = 120
REPLACE_ATTEMPTS = 60
REPLACE_DELAY_SECONDS = 1


def show_error(message):
    try:
        root = Tk()
        root.withdraw()
        messagebox.showerror("Ошибка обновления", message)
        root.destroy()
    except Exception:
        pass


def process_is_running(pid):
    if pid <= 0:
        return False
    if os.name == "nt":
        synchronize = 0x00100000
        wait_timeout = 0x00000102
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == wait_timeout
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def wait_for_process(pid):
    end_time = time.time() + WAIT_TIMEOUT_SECONDS
    while time.time() < end_time:
        if not process_is_running(pid):
            return True
        time.sleep(0.5)
    return False


def replace_program(source, target):
    backup = target.with_suffix(target.suffix + ".backup")
    if backup.exists():
        backup.unlink()
    if target.exists():
        shutil.copy2(target, backup)

    last_error = None
    for _ in range(REPLACE_ATTEMPTS):
        try:
            temp_target = target.with_suffix(target.suffix + ".new")
            if temp_target.exists():
                temp_target.unlink()
            shutil.copy2(source, temp_target)
            os.replace(temp_target, target)

            try:
                source.unlink()
            except OSError:
                pass

            if backup.exists():
                backup.unlink()
            return
        except Exception as error:
            last_error = error
            time.sleep(REPLACE_DELAY_SECONDS)

    if backup.exists():
        try:
            shutil.copy2(backup, target)
        except Exception:
            pass

    raise RuntimeError(f"Не удалось заменить программу: {last_error}")


def restart_program(program_path):
    subprocess.Popen(
        [str(program_path)],
        cwd=str(program_path.parent),
        close_fds=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--restart", required=True)
    args = parser.parse_args()

    source = Path(args.source).resolve()
    target = Path(args.target).resolve()
    restart = Path(args.restart).resolve()

    if not source.exists():
        raise FileNotFoundError(f"Не найден загруженный файл: {source}")

    if not wait_for_process(args.pid):
        raise RuntimeError("Основная программа не закрылась за 120 секунд")

    replace_program(source, target)
    restart_program(restart)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        show_error(str(error))
        sys.exit(1)
