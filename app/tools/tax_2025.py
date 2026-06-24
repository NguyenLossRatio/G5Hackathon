from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, Mapping, Tuple, Union

from pydantic import BaseModel

from app.guardrails.policy import GuardrailViolation, validate_filing_status
from app.tools.w2_parser import W2Data


FilingStatus = str
Bracket = Tuple[Decimal, Decimal]

# Source: IRS, One Big Beautiful Bill provisions for individuals and workers,
# tax year 2025 standard deduction increases.
# https://www.irs.gov/newsroom/one-big-beautiful-bill-provisions-individuals-and-workers
STANDARD_DEDUCTIONS: Dict[FilingStatus, Decimal] = {
    "single": Decimal("15750"),
    "married_filing_separately": Decimal("15750"),
    "married_filing_jointly": Decimal("31500"),
    "head_of_household": Decimal("23625"),
}

# Source: IRS, tax inflation adjustments for tax year 2025, ordinary income
# marginal tax rate thresholds.
# https://www.irs.gov/newsroom/irs-releases-tax-inflation-adjustments-for-tax-year-2025
TAX_BRACKETS: Dict[FilingStatus, Tuple[Bracket, ...]] = {
    "single": (
        (Decimal("0"), Decimal("0.10")),
        (Decimal("11925"), Decimal("0.12")),
        (Decimal("48475"), Decimal("0.22")),
        (Decimal("103350"), Decimal("0.24")),
        (Decimal("197300"), Decimal("0.32")),
        (Decimal("250525"), Decimal("0.35")),
        (Decimal("626350"), Decimal("0.37")),
    ),
    "married_filing_jointly": (
        (Decimal("0"), Decimal("0.10")),
        (Decimal("23850"), Decimal("0.12")),
        (Decimal("96950"), Decimal("0.22")),
        (Decimal("206700"), Decimal("0.24")),
        (Decimal("394600"), Decimal("0.32")),
        (Decimal("501050"), Decimal("0.35")),
        (Decimal("751600"), Decimal("0.37")),
    ),
    "married_filing_separately": (
        (Decimal("0"), Decimal("0.10")),
        (Decimal("11925"), Decimal("0.12")),
        (Decimal("48475"), Decimal("0.22")),
        (Decimal("103350"), Decimal("0.24")),
        (Decimal("197300"), Decimal("0.32")),
        (Decimal("250525"), Decimal("0.35")),
        (Decimal("375800"), Decimal("0.37")),
    ),
    "head_of_household": (
        (Decimal("0"), Decimal("0.10")),
        (Decimal("17000"), Decimal("0.12")),
        (Decimal("64850"), Decimal("0.22")),
        (Decimal("103350"), Decimal("0.24")),
        (Decimal("197300"), Decimal("0.32")),
        (Decimal("250500"), Decimal("0.35")),
        (Decimal("626350"), Decimal("0.37")),
    ),
}


class TaxReturnSummary(BaseModel):
    filing_status: str
    wages: int
    agi: int
    standard_deduction: int
    taxable_income: int
    tax: int
    federal_withholding: int
    refund: int
    amount_owed: int


def calculate_tax_return(w2: Union[W2Data, Mapping[str, object]], filing_status: str) -> TaxReturnSummary:
    normalized_status = validate_filing_status(filing_status)
    wages = _whole_dollars(_field(w2, "box_1_wages"))
    federal_withholding = _whole_dollars(_field(w2, "federal_income_tax_withheld"))
    standard_deduction = STANDARD_DEDUCTIONS[normalized_status]
    agi = Decimal(wages)
    taxable_income = max(Decimal("0"), agi - standard_deduction)
    tax = calculate_tax(taxable_income, normalized_status)
    difference = federal_withholding - tax

    return TaxReturnSummary(
        filing_status=normalized_status,
        wages=wages,
        agi=wages,
        standard_deduction=int(standard_deduction),
        taxable_income=int(taxable_income),
        tax=tax,
        federal_withholding=federal_withholding,
        refund=max(difference, 0),
        amount_owed=max(-difference, 0),
    )


def calculate_tax(taxable_income: Union[int, float, Decimal], filing_status: str) -> int:
    normalized_status = validate_filing_status(filing_status)
    income = max(Decimal("0"), _decimal(taxable_income))
    tax = Decimal("0")
    brackets = TAX_BRACKETS[normalized_status]

    for index, (floor, rate) in enumerate(brackets):
        next_floor = brackets[index + 1][0] if index + 1 < len(brackets) else None
        if income <= floor:
            break
        bracket_ceiling = income if next_floor is None else min(income, next_floor)
        tax += (bracket_ceiling - floor) * rate
        if next_floor is not None and income <= next_floor:
            break

    # Deterministic final-dollar rounding: round half up with Decimal, avoiding
    # Python's banker's rounding for x.5 values.
    return int(tax.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _field(w2: Union[W2Data, Mapping[str, object]], name: str) -> object:
    if isinstance(w2, Mapping):
        return w2[name]
    return getattr(w2, name)


def _whole_dollars(value: object) -> int:
    return int(_decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise GuardrailViolation("Tax input must be a finite number.", "invalid_tax_number")

    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise GuardrailViolation("Tax input must be a finite number.", "invalid_tax_number")

    if not number.is_finite():
        raise GuardrailViolation("Tax input must be a finite number.", "invalid_tax_number")
    return number
