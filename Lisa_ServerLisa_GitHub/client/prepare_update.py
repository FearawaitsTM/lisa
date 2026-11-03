import argparse
import hashlib
import json
import shutil
from pathlib import Path

from client.constants import CURRENT_VERSION


def calculate_sha256(file_path):
    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def main():
    parser = argparse.ArgumentParser(description="Подготовить обновление клиента Лиса")
    parser.add_argument("--exe", required=True, help="Путь к собранному Lisa.exe")
    parser.add_argument("--output", required=True, help="Папка пакета обновления")
    parser.add_argument("--manifest", default="updates/version.json")
    args = parser.parse_args()

    source_exe = Path(args.exe).resolve()
    output_dir = Path(args.output).resolve()
    manifest_path = Path(args.manifest).resolve()

    if not source_exe.is_file():
        raise FileNotFoundError(f"Не найден собранный клиент: {source_exe}")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Не найден манифест обновления: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    manifest_version = str(manifest.get("version", "")).strip()
    if manifest_version != CURRENT_VERSION:
        raise RuntimeError(
            f"Версия клиента {CURRENT_VERSION}, а в version.json указана {manifest_version}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    target_exe = output_dir / "Лиса.exe"
    shutil.copy2(source_exe, target_exe)

    manifest["version"] = CURRENT_VERSION
    manifest["sha256"] = calculate_sha256(target_exe)
    target_manifest = output_dir / "version.json"
    target_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Готов пакет обновления {CURRENT_VERSION}: {output_dir}")
    print(f"SHA256: {manifest['sha256']}")


if __name__ == "__main__":
    main()
