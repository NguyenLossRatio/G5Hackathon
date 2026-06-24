from decimal import Decimal, ROUND_HALF_UP

import pytest

from app.guardrails.policy import GuardrailViolation
from app.tools.tax_2025 import calculate_tax, calculate_tax_return
from app.tools.w2_parser import W2Data


TEST_BRACKETS = {
    "single": (
        (11_925, "0.10"),
        (48_475, "0.12"),
        (103_350, "0.22"),
        (197_300, "0.24"),
        (250_525, "0.32"),
        (626_350, "0.35"),
        (None, "0.37"),
    ),
    "married_filing_jointly": (
        (23_850, "0.10"),
        (96_950, "0.12"),
        (206_700, "0.22"),
        (394_600, "0.24"),
        (501_050, "0.32"),
        (751_600, "0.35"),
        (None, "0.37"),
    ),
    "married_filing_separately": (
        (11_925, "0.10"),
        (48_475, "0.12"),
        (103_350, "0.22"),
        (197_300, "0.24"),
        (250_525, "0.32"),
        (375_800, "0.35"),
        (None, "0.37"),
    ),
    "head_of_household": (
        (17_000, "0.10"),
        (64_850, "0.12"),
        (103_350, "0.22"),
        (197_300, "0.24"),
        (250_500, "0.32"),
        (626_350, "0.35"),
        (None, "0.37"),
    ),
}


def make_w2(**overrides):
    values = {
        "tax_year": 2025,
        "is_fake": True,
        "document_count": 1,
        "employee_name": "Jordan Sample",
        "employee_ssn": "000-00-0000",
        "employee_address": "123 Demo Lane, Springfield, IL 62704",
        "employer_name": "Example Payroll LLC",
        "employer_ein": "00-0000000",
        "employer_address": "456 Prototype Ave, Chicago, IL 60601",
        "box_1_wages": 40_000,
        "federal_income_tax_withheld": 3_200,
        "box_3_social_security_wages": 40_000,
        "social_security_tax_withheld": 2_480,
        "medicare_wages": 40_000,
        "medicare_tax_withheld": 580,
    }
    values.update(overrides)
    return W2Data(**values)


def summary_dict(summary):
    if hasattr(summary, "model_dump"):
        return summary.model_dump()
    return summary.dict()


def expected_tax_from_upper_limits(taxable_income, status):
    remaining = Decimal(str(taxable_income))
    lower_limit = Decimal("0")
    tax = Decimal("0")

    for upper_limit, rate in TEST_BRACKETS[status]:
        if remaining <= 0:
            break
        ceiling = remaining if upper_limit is None else min(remaining, Decimal(str(upper_limit)) - lower_limit)
        tax += ceiling * Decimal(rate)
        remaining -= ceiling
        if upper_limit is not None:
            lower_limit = Decimal(str(upper_limit))

    return int(tax.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def test_calculate_tax_return_for_single_sample_w2():
    summary = calculate_tax_return(make_w2(), "single")

    assert summary_dict(summary) == {
        "filing_status": "single",
        "wages": 40_000,
        "agi": 40_000,
        "standard_deduction": 15_750,
        "taxable_income": 24_250,
        "tax": 2_672,
        "federal_withholding": 3_200,
        "refund": 528,
        "amount_owed": 0,
    }


@pytest.mark.parametrize(
    "status,standard_deduction,taxable_income",
    [
        ("married_filing_jointly", 31_500, 8_500),
        ("married_filing_separately", 15_750, 24_250),
        ("head_of_household", 23_625, 16_375),
    ],
)
def test_calculate_tax_return_applies_status_specific_standard_deductions(
    status,
    standard_deduction,
    taxable_income,
):
    summary = calculate_tax_return(make_w2(), status)

    assert summary.standard_deduction == standard_deduction
    assert summary.taxable_income == taxable_income


def test_calculate_tax_return_accepts_dict_w2_and_normalizes_filing_status():
    summary = calculate_tax_return(
        {
            "box_1_wages": 40_000,
            "federal_income_tax_withheld": 3_200,
        },
        "Head Of Household",
    )

    assert summary.filing_status == "head_of_household"
    assert summary.wages == 40_000
    assert summary.taxable_income == 16_375


def test_calculate_tax_uses_single_second_marginal_bracket():
    assert calculate_tax(11_925, "single") == 1_193
    assert calculate_tax(12_000, "single") == 1_202
    assert calculate_tax(24_250, "single") == 2_672


@pytest.mark.parametrize(
    "status,taxable_income,explicit_expected",
    [
        ("married_filing_jointly", 23_850, 2_385),
        ("married_filing_jointly", 23_851, 2_385),
        ("married_filing_jointly", 96_950, 11_157),
        ("married_filing_jointly", 96_951, 11_157),
        ("married_filing_separately", 375_800, None),
        ("married_filing_separately", 375_801, None),
        ("head_of_household", 17_000, None),
        ("head_of_household", 64_850, None),
        ("head_of_household", 250_500, None),
        ("head_of_household", 626_350, None),
    ],
)
def test_calculate_tax_matches_bracket_boundaries_for_supported_statuses(
    status,
    taxable_income,
    explicit_expected,
):
    expected = explicit_expected
    if expected is None:
        expected = expected_tax_from_upper_limits(taxable_income, status)

    assert calculate_tax(taxable_income, status) == expected


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf"), True, None, "not-a-number"],
)
def test_calculate_tax_rejects_invalid_numeric_inputs(value):
    with pytest.raises(GuardrailViolation) as excinfo:
        calculate_tax(value, "single")

    assert excinfo.value.message == "Tax input must be a finite number."
    assert excinfo.value.code == "invalid_tax_number"


@pytest.mark.parametrize(
    "field",
    ["box_1_wages", "federal_income_tax_withheld"],
)
@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf"), True, None, "not-a-number"],
)
def test_calculate_tax_return_rejects_invalid_w2_numeric_inputs(field, value):
    with pytest.raises(GuardrailViolation) as excinfo:
        calculate_tax_return(
            {
                "box_1_wages": 40_000,
                "federal_income_tax_withheld": 3_200,
                field: value,
            },
            "single",
        )

    assert excinfo.value.message == "Tax input must be a finite number."
    assert excinfo.value.code == "invalid_tax_number"


def test_calculate_tax_returns_zero_for_no_taxable_income():
    assert calculate_tax(0, "single") == 0


def test_calculate_tax_rejects_unsupported_filing_status():
    with pytest.raises(GuardrailViolation):
        calculate_tax(10_000, "qualifying_surviving_spouse")
