import pytest

from app.guardrails.policy import GuardrailViolation
from app.tools.tax_2025 import calculate_tax, calculate_tax_return
from app.tools.w2_parser import W2Data


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


def test_calculate_tax_return_for_single_sample_w2():
    summary = calculate_tax_return(make_w2(), "single")

    assert summary_dict(summary) == {
        "filing_status": "single",
        "wages": 40_000,
        "agi": 40_000,
        "standard_deduction": 15_750,
        "taxable_income": 24_250,
        "tax": 2_669,
        "federal_withholding": 3_200,
        "refund": 531,
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


def test_calculate_tax_returns_zero_for_no_taxable_income():
    assert calculate_tax(0, "single") == 0


def test_calculate_tax_rejects_unsupported_filing_status():
    with pytest.raises(GuardrailViolation):
        calculate_tax(10_000, "qualifying_surviving_spouse")
