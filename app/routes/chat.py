from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.agent.engine import SAMPLE_W2_PATH, SessionNotFound, handle_message, start_session, upload_w2
from app.storage import db


router = APIRouter()


class ChatMessageRequest(BaseModel):
    session_id: str
    message: Optional[str] = None
    answer: Any = None


@router.post("/api/chat/start")
def start_chat():
    return start_session()


@router.post("/api/chat/message")
def post_message(request: ChatMessageRequest):
    try:
        return handle_message(request.session_id, message=request.message, answer=request.answer)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc


@router.post("/api/chat/upload-w2")
async def post_w2_upload(
    session_id: str = Form(...),
    use_sample: bool = Form(False),
    file: Optional[UploadFile] = File(None),
):
    try:
        path = SAMPLE_W2_PATH if use_sample else await _save_upload(file)
        return upload_w2(session_id, path)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc


@router.get("/api/sessions/{session_id}/events")
def session_events(session_id: str):
    return {"events": list(db.list_events(session_id))}


async def _save_upload(file: Optional[UploadFile]) -> Path:
    if file is None:
        raise HTTPException(status_code=400, detail="Upload file or use_sample=true is required")
    upload_dir = Path(__file__).resolve().parents[2] / "var" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "uploaded-w2.pdf").name
    destination = upload_dir / safe_name
    destination.write_bytes(await file.read())
    return destination
