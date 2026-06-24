import re
from typing import Any, Dict, Tuple, Union


class GuardrailViolation(Exception):
    def __init__(self, message: str, code: str = "guardrail_violation") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


ALLOWED_FILING_STATUSES = {
    "single": "single",
    "married filing jointly": "married_filing_jointly",
    "married_filing_jointly": "married_filing_jointly",
    "married filing separately": "married_filing_separately",
    "married_filing_separately": "married_filing_separately",
    "head of household": "head_of_household",
    "head_of_household": "head_of_household",
}

_OUT_OF_SCOPE_PATTERNS = (
    ("e_filing", r"\be[-\s]?fil(?:e|ing)\b|\belectronic(?:ally)?\s+fil(?:e|ing)\b"),
    ("state_return", r"\bstate\s+(?:return|filing|tax|taxes)\b|\b(?:california|new york|texas|florida)\s+(?:return|filing|tax|taxes)\b"),
    ("real_tax_advice", r"\breal\s+tax\s+advice\b|\btax\s+advice\b|\bwhat\s+should\s+i\b|\brecommend(?:ation)?\b"),
    ("multiple_income_documents", r"\b(?:two|three|multiple|several)\s+(?:w-?2s?|income documents?)\b|\b1099\b|\bsecond\s+w-?2\b|\banother\s+w-?2\b"),
    ("self_employment", r"\bself[-\s]?employ(?:ed|ment)\b|\bschedule\s+c\b|\bbusiness\s+income\b|\bfreelanc"),
    ("capital_gains", r"\bcapital\s+gains?\b|\bsold\s+(?:stock|shares|crypto|bitcoin)\b|\b1099-?b\b|\bbrokerage\b"),
    ("real_identity_data", r"\b\d{3}-\d{2}-\d{4}\b|\bssn\b|\bsocial security number\b|\breal\s+(?:identity|name|address|pii)\b|\bdate of birth\b"),
    ("itemized_deductions", r"\bitemiz(?:e|ed|ing)\b|\bschedule\s+a\b"),
)


def validate_scope_message(message: str) -> None:
    normalized = _normalize_text(message)
    for year in re.findall(r"\b20\d{2}\b", normalized):
        if year != "2025":
            raise GuardrailViolation("Only tax year 2025 is supported.", "unsupported_tax_year")

    if re.search(r"\breal\s+fil(?:e|ing)\b|\bsubmit\s+(?:to|with)\s+(?:the\s+)?irs\b", normalized):
        raise GuardrailViolation("Real filing is outside this prototype scope.", "real_filing")

    for code, pattern in _OUT_OF_SCOPE_PATTERNS:
        if re.search(pattern, normalized):
            raise GuardrailViolation(_message_for_code(code), code)


def validate_w2_data(w2: Dict[str, Any]) -> None:
    if not isinstance(w2, dict):
        raise GuardrailViolation("W-2 data must be a dictionary.", "invalid_w2")

    if w2.get("tax_year") != 2025:
        raise GuardrailViolation("Only tax year 2025 is supported.", "unsupported_tax_year")
    if w2.get("is_fake") is not True:
        raise GuardrailViolation("Only fake W-2 data is accepted.", "real_w2")
    if int(w2.get("document_count", 1)) != 1:
        raise GuardrailViolation("Only one W-2 document is supported.", "multiple_income_documents")

    wages = _required_number(w2, ("box_1_wages", "wages", "box1_wages"))
    withholding = _required_number(
        w2,
        ("federal_income_tax_withheld", "federal_withholding", "box_2_federal_withholding"),
    )
    social_security_wages = _required_number(
        w2,
        ("box_3_social_security_wages", "social_security_wages", "box3_social_security_wages"),
    )

    if wages < 30_000 or wages > 50_000:
        raise GuardrailViolation("Wages must be between $30,000 and $50,000.", "wages_out_of_range")
    if withholding < 0 or withholding > 8_000:
        raise GuardrailViolation(
            "Federal withholding must be between $0 and $8,000.",
            "withholding_out_of_range",
        )
    if social_security_wages < wages:
        raise GuardrailViolation(
            "Social Security wages cannot be less than box 1 wages.",
            "social_security_wages_out_of_range",
        )


def validate_filing_status(status: str) -> str:
    normalized = _normalize_text(status).replace("-", " ").replace("  ", " ")
    normalized = normalized.replace(" ", "_") if normalized in {"single"} else normalized
    normalized = ALLOWED_FILING_STATUSES.get(normalized)
    if normalized is None:
        raise GuardrailViolation("Unsupported filing status.", "unsupported_filing_status")
    return normalized


def validate_digital_assets(value: object) -> bool:
    if not isinstance(value, bool):
        raise GuardrailViolation("Digital asset answer must be true or false.", "invalid_boolean")
    return value


def validate_refund_choice(choice: Union[Dict[str, Any], str]) -> Union[Dict[str, Any], str]:
    if isinstance(choice, str):
        normalized = _normalize_text(choice)
        if normalized == "paper_check":
            return "paper_check"
        if normalized == "paper check":
            return "paper_check"
        raise GuardrailViolation("Unsupported refund choice.", "unsupported_refund_choice")

    if not isinstance(choice, dict):
        raise GuardrailViolation("Refund choice must be paper_check or a dictionary.", "invalid_refund_choice")

    method = _normalize_text(str(choice.get("method", "")))
    if method != "direct_deposit":
        raise GuardrailViolation("Only paper check or fake direct deposit is supported.", "unsupported_refund_choice")

    routing = str(choice.get("routing_number", ""))
    account = str(choice.get("account_number", ""))
    if not _is_fake_routing_number(routing) or not _is_fake_account_number(account):
        raise GuardrailViolation(
            "Direct deposit values must be obvious fake/test values.",
            "real_looking_bank_details",
        )
    return choice


def _normalize_text(value: object) -> str:
    return str(value or "").strip().lower()


def _message_for_code(code: str) -> str:
    messages = {
        "e_filing": "E-filing is outside this prototype scope.",
        "state_return": "State returns are outside this prototype scope.",
        "real_tax_advice": "Real tax advice is outside this prototype scope.",
        "multiple_income_documents": "Only one fake W-2 is supported.",
        "self_employment": "Self-employment income is outside this prototype scope.",
        "capital_gains": "Capital gains are outside this prototype scope.",
        "real_identity_data": "Real identity data is not accepted.",
        "itemized_deductions": "Itemized deductions are outside this prototype scope.",
    }
    return messages.get(code, "Request is outside this prototype scope.")


def _required_number(w2: Dict[str, Any], keys: Tuple[str, ...]) -> float:
    for key in keys:
        if key in w2:
            value = w2[key]
            break
    else:
        raise GuardrailViolation("Missing required W-2 numeric field.", "missing_w2_field")

    if isinstance(value, bool):
        raise GuardrailViolation("W-2 numeric field must be a number.", "invalid_w2_number")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise GuardrailViolation("W-2 numeric field must be a number.", "invalid_w2_number")


def _is_fake_routing_number(value: str) -> bool:
    return bool(re.fullmatch(r"0{9}|000\d{6}", value))


def _is_fake_account_number(value: str) -> bool:
    return bool(re.fullmatch(r"0{3,17}|000\d{6,14}", value))
