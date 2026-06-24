import pytest

from app.guardrails.policy import (
    GuardrailViolation,
    validate_digital_assets,
    validate_filing_status,
    validate_refund_choice,
    validate_scope_message,
    validate_w2_data,
)


@pytest.mark.parametrize(
    "message",
    [
        "Use one fake W-2 for tax year 2025 to prepare a federal Form 1040 demo.",
        "Show me tax year 2025 federal Form 1040 demo",
        "withholding or tax withheld",
        "withholding OR tax withheld",
        "wages OR tax withheld",
    ],
)
def test_scope_accepts_in_scope_demo_messages(message):
    validate_scope_message(message)


@pytest.mark.parametrize(
    "message,code",
    [
        ("Can you e-file this return for me?", "e_filing"),
        ("Please prepare my California state filing too.", "state_return"),
        ("What real tax advice should I follow?", "real_tax_advice"),
        ("I have two W-2s and a 1099 to upload.", "multiple_income_documents"),
        ("Add my self-employment Schedule C income.", "self_employment"),
        ("I sold stock and need capital gains reported.", "capital_gains"),
        ("Use my real SSN 123-45-6789 and bank account.", "real_identity_data"),
        ("Let's itemize deductions instead of taking the standard deduction.", "itemized_deductions"),
        ("Prepare this for tax year 2024.", "unsupported_tax_year"),
        ("federal Form 1040-NR", "form_1040_variant"),
        ("Please file my real tax return.", "real_filing"),
        ("Please prepare my Illinois filing.", "state_return"),
        ("Use my legal name Alan Smith and home address 123 Main St.", "real_identity_data"),
        ("Please file this return with the IRS.", "real_filing"),
        ("Please file this tax return for me.", "real_filing"),
        ("Please mail this return to the IRS.", "real_filing"),
        ("Submit this tax return for me.", "real_filing"),
        ("Can you prepare my state income tax return?", "state_return"),
        ("Can you do my state income taxes?", "state_return"),
        ("Prepare my NY tax return.", "state_return"),
        ("Prepare my OR state return.", "state_return"),
        ("Prepare my ny tax return.", "state_return"),
        ("Prepare my Ca tax return.", "state_return"),
        ("Can you file my or state return?", "state_return"),
        ("My DOB is 01/02/1990.", "real_identity_data"),
        ("Use my actual name Alan Smith.", "real_identity_data"),
        ("Use my address 742 Evergreen Terrace.", "real_identity_data"),
    ],
)
def test_scope_rejects_out_of_scope_requests(message, code):
    with pytest.raises(GuardrailViolation) as excinfo:
        validate_scope_message(message)
    assert excinfo.value.code == code


def valid_w2(**overrides):
    w2 = {
        "tax_year": 2025,
        "is_fake": True,
        "document_count": 1,
        "box_1_wages": 40_000,
        "federal_income_tax_withheld": 3_200,
        "box_3_social_security_wages": 40_000,
    }
    w2.update(overrides)
    return w2


def test_w2_accepts_one_fake_2025_document_in_demo_ranges():
    validate_w2_data(valid_w2())


@pytest.mark.parametrize(
    "overrides",
    [
        {"tax_year": 2026},
        {"is_fake": False},
        {"document_count": 2},
        {"box_1_wages": 29_999.99},
        {"box_1_wages": 50_000.01},
        {"federal_income_tax_withheld": -0.01},
        {"federal_income_tax_withheld": 8_000.01},
        {"box_3_social_security_wages": 39_999.99},
    ],
)
def test_w2_rejects_values_outside_demo_scope(overrides):
    with pytest.raises(GuardrailViolation):
        validate_w2_data(valid_w2(**overrides))


@pytest.mark.parametrize("document_count", ["two", None, True, False])
def test_w2_rejects_invalid_document_count_values(document_count):
    with pytest.raises(GuardrailViolation) as excinfo:
        validate_w2_data(valid_w2(document_count=document_count))
    assert excinfo.value.code == "invalid_document_count"


@pytest.mark.parametrize(
    "field,value",
    [
        ("box_1_wages", float("nan")),
        ("box_1_wages", "nan"),
        ("box_1_wages", float("inf")),
        ("box_1_wages", "-inf"),
        ("federal_income_tax_withheld", float("nan")),
        ("federal_income_tax_withheld", "nan"),
        ("federal_income_tax_withheld", float("inf")),
        ("federal_income_tax_withheld", "-inf"),
        ("box_3_social_security_wages", float("nan")),
        ("box_3_social_security_wages", "nan"),
        ("box_3_social_security_wages", float("inf")),
        ("box_3_social_security_wages", "-inf"),
    ],
)
def test_w2_rejects_non_finite_numeric_values(field, value):
    with pytest.raises(GuardrailViolation) as excinfo:
        validate_w2_data(valid_w2(**{field: value}))
    assert excinfo.value.code == "invalid_w2_number"


@pytest.mark.parametrize(
    "raw,normalized",
    [
        ("single", "single"),
        ("married filing jointly", "married_filing_jointly"),
        ("married_filing_separately", "married_filing_separately"),
        ("Head Of Household", "head_of_household"),
    ],
)
def test_filing_status_accepts_supported_statuses(raw, normalized):
    assert validate_filing_status(raw) == normalized


def test_filing_status_rejects_unsupported_status():
    with pytest.raises(GuardrailViolation):
        validate_filing_status("qualifying_surviving_spouse")


@pytest.mark.parametrize("value,expected", [(True, True), (False, False)])
def test_digital_assets_accepts_booleans(value, expected):
    assert validate_digital_assets(value) is expected


@pytest.mark.parametrize("value", ["yes", "false", 1, None])
def test_digital_assets_rejects_non_booleans(value):
    with pytest.raises(GuardrailViolation):
        validate_digital_assets(value)


def test_refund_choice_accepts_paper_check():
    assert validate_refund_choice("paper_check") == "paper_check"


def test_refund_choice_accepts_fake_direct_deposit_values():
    choice = {
        "method": "direct_deposit",
        "routing_number": "000000000",
        "account_number": "000123456789",
    }

    assert validate_refund_choice(choice) == choice


@pytest.mark.parametrize(
    "choice",
    [
        {
            "method": "direct_deposit",
            "routing_number": "021000021",
            "account_number": "123456789012",
        },
        {
            "method": "direct_deposit",
            "routing_number": "000000000",
            "account_number": "9876543210",
        },
        {"method": "wire", "routing_number": "000000000", "account_number": "000123456789"},
    ],
)
def test_refund_choice_rejects_real_looking_or_unsupported_values(choice):
    with pytest.raises(GuardrailViolation):
        validate_refund_choice(choice)
