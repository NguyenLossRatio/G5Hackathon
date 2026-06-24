import re
from pathlib import Path
from typing import Any, Dict, Union

import pdfplumber
from pydantic import BaseModel

from app.tools.observability import record_event


class W2ParseError(Exception):
    """Raised when the generated sample W-2 cannot be parsed."""


class W2Data(BaseModel):
    tax_year: int
    is_fake: bool
    document_count: int
    employee_name: str
    employee_ssn: str
    employee_address: str
    employer_name: str
    employer_ein: str
    employer_address: str
    box_1_wages: float
    federal_income_tax_withheld: float
    box_3_social_security_wages: float
    social_security_tax_withheld: float
    medicare_wages: float
    medicare_tax_withheld: float


def parse_w2_pdf(pdf_path: Union[str, Path], session_id: str) -> W2Data:
    path = Path(pdf_path)
    event_payload = _file_payload(path)
    record_event(session_id, "w2_parse_started", event_payload)

    try:
        if not path.exists():
            raise W2ParseError("W-2 PDF not found")

        text = _extract_text(path)
        w2 = W2Data(
            tax_year=_required_int(text, r"Tax Year\s+(\d{4})", "tax year"),
            is_fake=_required_bool(text, r"Fake Document\s+(True|False)", "fake document flag"),
            document_count=_required_int(text, r"Document Count\s+(\d+)", "document count"),
            employee_name=_required_text(text, r"Employee Name\s+(.+)", "employee name"),
            employee_ssn=_required_text(text, r"Employee SSN\s+(\d{3}-\d{2}-\d{4})", "employee SSN"),
            employee_address=_required_text(text, r"Employee Address\s+(.+)", "employee address"),
            employer_name=_required_text(text, r"Employer Name\s+(.+)", "employer name"),
            employer_ein=_required_text(text, r"Employer EIN\s+(\d{2}-\d{7})", "employer EIN"),
            employer_address=_required_text(text, r"Employer Address\s+(.+)", "employer address"),
            box_1_wages=_required_money(
                text,
                r"Box 1 Wages, tips, other compensation\s+(\$[\d,]+\.\d{2})",
                "box 1 wages",
            ),
            federal_income_tax_withheld=_required_money(
                text,
                r"Box 2 Federal income tax withheld\s+(\$[\d,]+\.\d{2})",
                "federal income tax withheld",
            ),
            box_3_social_security_wages=_required_money(
                text,
                r"Box 3 Social Security wages\s+(\$[\d,]+\.\d{2})",
                "box 3 Social Security wages",
            ),
            social_security_tax_withheld=_required_money(
                text,
                r"Box 4 Social Security tax withheld\s+(\$[\d,]+\.\d{2})",
                "Social Security tax withheld",
            ),
            medicare_wages=_required_money(
                text,
                r"Box 5 Medicare wages and tips\s+(\$[\d,]+\.\d{2})",
                "Medicare wages",
            ),
            medicare_tax_withheld=_required_money(
                text,
                r"Box 6 Medicare tax withheld\s+(\$[\d,]+\.\d{2})",
                "Medicare tax withheld",
            ),
        )
    except W2ParseError as exc:
        record_event(session_id, "w2_parse_failed", {**event_payload, "error": str(exc)})
        raise
    except Exception as exc:
        error = W2ParseError("Unable to parse W-2 PDF")
        record_event(session_id, "w2_parse_failed", {**event_payload, "error": str(error)})
        raise error from exc

    record_event(
        session_id,
        "w2_parse_succeeded",
        {**event_payload, "summary": _summary(w2)},
    )
    return w2


def _extract_text(path: Path) -> str:
    page_text = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text.append(page.extract_text() or "")
    text = "\n".join(page_text)
    if not text.strip():
        raise W2ParseError("W-2 PDF contained no extractable text")
    if "SAMPLE FAKE W-2 - NOT FOR FILING" not in text:
        raise W2ParseError("W-2 PDF is not the generated fake sample")
    return text


def _required_text(text: str, pattern: str, field_name: str) -> str:
    return _required_match(text, pattern, field_name).strip()


def _required_int(text: str, pattern: str, field_name: str) -> int:
    return int(_required_match(text, pattern, field_name))


def _required_bool(text: str, pattern: str, field_name: str) -> bool:
    return _required_match(text, pattern, field_name) == "True"


def _required_money(text: str, pattern: str, field_name: str) -> float:
    raw_value = _required_match(text, pattern, field_name)
    return float(raw_value.replace("$", "").replace(",", ""))


def _required_match(text: str, pattern: str, field_name: str) -> str:
    match = re.search(pattern, text)
    if match is None:
        raise W2ParseError(f"Missing {field_name}")
    return match.group(1)


def _file_payload(path: Path) -> Dict[str, str]:
    return {
        "file_name": path.name,
        "source": "sample_w2",
    }


def _summary(w2: W2Data) -> Dict[str, Any]:
    return {
        "tax_year": w2.tax_year,
        "is_fake": w2.is_fake,
        "document_count": w2.document_count,
        "box_1_wages": w2.box_1_wages,
        "federal_income_tax_withheld": w2.federal_income_tax_withheld,
    }
