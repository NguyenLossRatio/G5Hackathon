from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.agent.engine import DownloadNotFound, resolve_download


router = APIRouter()


@router.get("/downloads/{download_id}")
def download_pdf(download_id: str):
    try:
        path = resolve_download(download_id)
    except DownloadNotFound as exc:
        raise HTTPException(status_code=404, detail="Download not found") from exc
    return FileResponse(path, media_type="application/pdf", filename=path.name)
