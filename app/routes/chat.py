from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.agent.engine import SAMPLE_W2_PATH, SessionNotFound, handle_message, start_session, upload_w2
from app.storage import db
from app.tools.w2_parser import W2ParseError


router = APIRouter()
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


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
    if db.load_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    uploaded_path: Optional[Path] = None
    try:
        path = SAMPLE_W2_PATH if use_sample else await _save_upload(session_id, file)
        if not use_sample:
            uploaded_path = path
        response = upload_w2(session_id, path)
        if uploaded_path is not None and response.get("phase") != "need_filing_status":
            _cleanup_upload(uploaded_path)
        return response
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    except W2ParseError as exc:
        _cleanup_upload(uploaded_path)
        raise HTTPException(status_code=400, detail=f"W-2 PDF could not be parsed: {exc}") from exc


@router.get("/api/sessions/{session_id}/events")
def session_events(session_id: str):
    return {"events": list(db.list_events(session_id))}


async def _save_upload(session_id: str, file: Optional[UploadFile]) -> Path:
    if file is None:
        raise HTTPException(status_code=400, detail="Upload file or use_sample=true is required")
    original_name = Path(file.filename or "").name
    if Path(original_name).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded W-2 PDF is too large")

    upload_dir = Path(__file__).resolve().parents[2] / "var" / "uploads" / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = upload_dir / f"w2-{uuid4().hex}.pdf"
    destination.write_bytes(content)
    return destination


def _cleanup_upload(path: Optional[Path]) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
