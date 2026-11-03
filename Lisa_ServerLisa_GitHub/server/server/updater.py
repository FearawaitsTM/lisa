from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .config import UPDATES_DIR

router = APIRouter()


@router.get("/updates/version.json")
def version_manifest():
    manifest = UPDATES_DIR / "version.json"
    if not manifest.exists():
        raise HTTPException(status_code=404, detail="version.json не найден")
    return FileResponse(
        manifest,
        media_type="application/json",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@router.get("/updates/{file_name}")
def update_file(file_name: str):
    path = UPDATES_DIR / file_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Файл обновления не найден")
    return FileResponse(
        path,
        filename=path.name,
        headers={"Cache-Control": "no-store"},
    )
