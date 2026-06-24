from pathlib import Path
from typing import Any, Dict, Mapping, Optional
from uuid import uuid4

from app.agent import messages
from app.agent.state import Phase, QuestionBudgetExceeded, TaxSession
from app.guardrails.policy import (
    GuardrailViolation,
    validate_digital_assets,
    validate_filing_status,
    validate_refund_choice,
    validate_scope_message,
    validate_w2_data,
)
from app.storage import db
from app.tools.form1040 import DEFAULT_GENERATED_DIR, generate_1040_pdf
from app.tools.observability import record_event
from app.tools.tax_2025 import calculate_tax_return
from app.tools.w2_parser import parse_w2_pdf


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_W2_PATH = REPO_ROOT / "assets" / "sample" / "sample-w2-2025.pdf"


class SessionNotFound(Exception):
    """Raised when a chat request references a missing session."""


class DownloadNotFound(Exception):
    """Raised when a download id does not map to a generated session PDF."""


def start_session() -> Dict[str, Any]:
    session = TaxSession(session_id=uuid4().hex)
    _ask_question(session, "need_w2")
    db.save_session(session)
    return _response(session, messages.w2_intake_question())


def upload_w2(session_id: str, pdf_path: Path) -> Dict[str, Any]:
    session = _load_session(session_id)
    try:
        w2 = parse_w2_pdf(pdf_path, session.session_id)
        w2_data = _model_dict(w2)
        validate_w2_data(w2_data)
        _record_guardrail_passed(session, "w2_data", _w2_summary(w2_data))
    except GuardrailViolation as exc:
        _record_guardrail_violation(session, exc, "w2_data")
        db.save_session(session)
        return _response(session, messages.refusal_message(exc.code))

    session.w2 = w2_data
    budget_response = _ask_required_question(session, "need_filing_status")
    if budget_response is not None:
        return budget_response
    db.save_session(session)
    return _response(session, messages.filing_status_question())


def handle_message(
    session_id: str,
    message: Optional[str] = None,
    answer: Any = None,
) -> Dict[str, Any]:
    session = _load_session(session_id)
    guardrail_text = _guardrail_text(message, answer)
    if guardrail_text is not None:
        try:
            validate_scope_message(guardrail_text)
        except GuardrailViolation as exc:
            _record_guardrail_violation(session, exc, "message")
            db.save_session(session)
            return _response(session, messages.refusal_message(exc.code))
        _record_guardrail_passed(session, "message", {"phase": session.phase, "length": len(guardrail_text)})

    value = answer if answer is not None else message
    try:
        if session.phase == "need_w2":
            return _retry_response(session)
        if session.phase == "need_filing_status":
            return _handle_filing_status(session, value)
        if session.phase == "need_household":
            return _handle_household(session, value)
        if session.phase == "need_digital_assets":
            return _handle_digital_assets(session, value)
        if session.phase == "need_refund":
            return _handle_refund(session, value)
        db.save_session(session)
        return _response(session, messages.retry_message(session.phase))
    except GuardrailViolation as exc:
        _record_guardrail_violation(session, exc, session.phase)
        return _retry_response(session)


def resolve_download(download_id: str) -> Path:
    if "/" in download_id or "\\" in download_id or ".." in download_id:
        raise DownloadNotFound("Unknown download")
    session_id = download_id.split(".", 1)[0]
    session = db.load_session(session_id)
    if session is None or session.download_id != download_id:
        raise DownloadNotFound("Unknown download")

    raw_path = session.answers.get("download_path")
    if not isinstance(raw_path, str):
        raise DownloadNotFound("Unknown download")
    path = Path(raw_path).expanduser().resolve()
    generated_dir = _generated_dir().resolve()
    if path.suffix.lower() != ".pdf" or not _is_relative_to(path, generated_dir) or not path.exists():
        raise DownloadNotFound("Unknown download")
    return path


def _handle_filing_status(session: TaxSession, value: Any) -> Dict[str, Any]:
    filing_status = validate_filing_status(str(value or ""))
    budget_response = _ask_required_question(session, "need_household")
    if budget_response is not None:
        return budget_response
    session.answers["filing_status"] = filing_status
    db.save_session(session)
    return _response(session, messages.household_question())


def _handle_household(session: TaxSession, value: Any) -> Dict[str, Any]:
    household = str(value or "").strip()
    budget_response = _ask_required_question(session, "need_digital_assets")
    if budget_response is not None:
        return budget_response
    session.answers["household"] = household
    db.save_session(session)
    return _response(session, messages.digital_assets_question())


def _handle_digital_assets(session: TaxSession, value: Any) -> Dict[str, Any]:
    digital_assets = validate_digital_assets(_coerce_bool(value))
    budget_response = _ask_required_question(session, "need_refund")
    if budget_response is not None:
        return budget_response
    session.answers["digital_assets"] = digital_assets
    db.save_session(session)
    return _response(session, messages.refund_question())


def _handle_refund(session: TaxSession, value: Any) -> Dict[str, Any]:
    refund_choice = validate_refund_choice(_coerce_refund_choice(value))
    session.answers["refund_choice"] = refund_choice
    _prepare_return(session)
    db.save_session(session)
    return _response(session, messages.complete_message(session.return_summary or {}))


def _prepare_return(session: TaxSession) -> None:
    if session.w2 is None:
        raise GuardrailViolation("A W-2 is required before preparing the return.", "missing_w2")

    filing_status = str(session.answers.get("filing_status") or "")
    record_event(
        session.session_id,
        "tax_calculation_started",
        {"input_summary": {"filing_status": filing_status, "w2": _w2_summary(session.w2)}},
    )
    try:
        summary = calculate_tax_return(session.w2, filing_status)
    except Exception as exc:
        record_event(
            session.session_id,
            "tax_calculation_failed",
            {
                "input_summary": {"filing_status": filing_status},
                "failure_summary": {"error": str(exc)},
            },
        )
        raise

    summary_data = _model_dict(summary)
    session.return_summary = summary_data
    record_event(
        session.session_id,
        "tax_calculation_succeeded",
        {"result_summary": _return_summary(summary_data)},
    )

    taxpayer = {
        "name": session.w2["employee_name"],
        "ssn": session.w2["employee_ssn"],
        "address": session.w2["employee_address"],
    }
    refund_choice = _form_refund_choice(session.answers["refund_choice"])
    download_id = f"{session.session_id}.{uuid4().hex}"
    output_dir = _generated_dir() / session.session_id / download_id
    record_event(
        session.session_id,
        "form_generation_started",
        {
            "input_summary": {
                "download_id": download_id,
                "filing_status": filing_status,
                "digital_assets": session.answers.get("digital_assets"),
                "refund_method": refund_choice["method"],
            }
        },
    )
    try:
        pdf_path = generate_1040_pdf(
            taxpayer=taxpayer,
            filing_status=filing_status,
            digital_assets=bool(session.answers.get("digital_assets")),
            refund_choice=refund_choice,
            w2=session.w2,
            summary=summary_data,
            output_dir=output_dir,
            output_filename="completed-1040-2025.pdf",
        )
    except Exception as exc:
        record_event(
            session.session_id,
            "form_generation_failed",
            {
                "input_summary": {"filing_status": filing_status},
                "failure_summary": {"error": str(exc)},
            },
        )
        raise

    session.download_id = download_id
    session.answers["download_path"] = str(pdf_path.resolve())
    _transition_to(session, "complete")
    record_event(
        session.session_id,
        "form_generation_succeeded",
        {"result_summary": {"download_id": download_id, "file_name": pdf_path.name}},
    )


def _ask_question(session: TaxSession, next_phase: Phase) -> None:
    previous_phase = session.phase
    previous_count = session.question_count
    session.ask_question(next_phase)
    record_event(
        session.session_id,
        "state_transition",
        {
            "from": previous_phase,
            "to": session.phase,
            "question_count": session.question_count,
            "question_incremented": session.question_count == previous_count + 1,
        },
    )


def _transition_to(session: TaxSession, next_phase: Phase) -> None:
    previous_phase = session.phase
    session.transition_to(next_phase)
    record_event(
        session.session_id,
        "state_transition",
        {
            "from": previous_phase,
            "to": session.phase,
            "question_count": session.question_count,
            "question_incremented": False,
        },
    )


def _response(session: TaxSession, message: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "session_id": session.session_id,
        "message": message,
        "phase": session.phase,
        "question_count": session.question_count,
        "actions": _actions_for_phase(session.phase),
    }
    if session.phase == "complete" and session.download_id:
        payload["download_url"] = f"/downloads/{session.download_id}"
    return payload


def _ask_required_question(session: TaxSession, next_phase: Phase) -> Optional[Dict[str, Any]]:
    try:
        _ask_question(session, next_phase)
    except QuestionBudgetExceeded as exc:
        return _budget_response(session, exc)
    return None


def _retry_response(session: TaxSession) -> Dict[str, Any]:
    try:
        _ask_question(session, session.phase)
        message = messages.retry_message(session.phase)
    except QuestionBudgetExceeded as exc:
        return _budget_response(session, exc)
    db.save_session(session)
    return _response(session, message)


def _budget_response(session: TaxSession, exc: QuestionBudgetExceeded) -> Dict[str, Any]:
    record_event(
        session.session_id,
        "question_budget_exceeded",
        {
            "input_summary": {
                "phase": session.phase,
                "question_count": session.question_count,
            },
            "failure_summary": {"error": str(exc)},
        },
    )
    db.save_session(session)
    return _response(session, messages.question_budget_message())


def _actions_for_phase(phase: str) -> list:
    return {
        "need_w2": ["upload_w2", "use_sample_w2"],
        "need_filing_status": [
            "single",
            "married_filing_jointly",
            "married_filing_separately",
            "head_of_household",
        ],
        "need_household": ["answer_household"],
        "need_digital_assets": ["yes", "no"],
        "need_refund": ["paper_check", "direct_deposit"],
        "complete": ["download_pdf"],
    }.get(phase, [])


def _load_session(session_id: str) -> TaxSession:
    session = db.load_session(session_id)
    if session is None:
        raise SessionNotFound(f"Session not found: {session_id}")
    return session


def _guardrail_text(message: Optional[str], answer: Any) -> Optional[str]:
    if message is not None:
        return message
    if isinstance(answer, str):
        return answer
    return None


def _record_guardrail_passed(session: TaxSession, subject: str, input_summary: Mapping[str, Any]) -> None:
    record_event(
        session.session_id,
        "guardrail_check",
        {"subject": subject, "status": "passed", "input_summary": dict(input_summary)},
    )


def _record_guardrail_violation(session: TaxSession, exc: GuardrailViolation, subject: str) -> None:
    payload = {"subject": subject, "status": "failed", "code": exc.code, "message": exc.message}
    record_event(session.session_id, "guardrail_check", payload)
    record_event(session.session_id, "guardrail_violation", payload)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"yes", "y", "true"}:
        return True
    if normalized in {"no", "n", "false"}:
        return False
    return value


def _coerce_refund_choice(value: Any) -> Any:
    if isinstance(value, Mapping):
        method = str(value.get("method") or "").strip().lower().replace("-", " ")
        if method in {"paper_check", "paper check"}:
            return "paper_check"
        return value
    if isinstance(value, str):
        if _is_paper_check_text(value):
            return "paper_check"
    return value


def _is_paper_check_text(value: str) -> bool:
    normalized = " ".join(value.strip().lower().replace("-", " ").replace("_", " ").split())
    return normalized == "check" or "paper check" in normalized


def _form_refund_choice(value: Any) -> Dict[str, Any]:
    if value == "paper_check":
        return {"method": "paper_check"}
    if isinstance(value, Mapping):
        return dict(value)
    return {"method": "paper_check"}


def _model_dict(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return dict(value)


def _w2_summary(w2: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "tax_year": w2.get("tax_year"),
        "is_fake": w2.get("is_fake"),
        "document_count": w2.get("document_count"),
        "box_1_wages": w2.get("box_1_wages"),
        "federal_income_tax_withheld": w2.get("federal_income_tax_withheld"),
    }


def _return_summary(summary: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "filing_status": summary.get("filing_status"),
        "tax": summary.get("tax"),
        "federal_withholding": summary.get("federal_withholding"),
        "refund": summary.get("refund"),
        "amount_owed": summary.get("amount_owed"),
    }


def _generated_dir() -> Path:
    import os

    configured_dir = os.environ.get("TAX_ASSISTANT_GENERATED_DIR")
    if configured_dir:
        return Path(configured_dir).expanduser()
    return DEFAULT_GENERATED_DIR


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
