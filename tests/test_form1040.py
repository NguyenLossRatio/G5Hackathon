from pathlib import Path

import pdfplumber
from pypdf import PdfReader

from app.tools.form1040 import RefundChoice, TaxpayerInfo, generate_1040_pdf
from app.tools.tax_2025 import calculate_tax_return
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


def test_generate_1040_pdf_creates_extractable_completed_return(tmp_path):
    w2 = make_w2()
    summary = calculate_tax_return(w2, "single")

    generated_path = generate_1040_pdf(
        taxpayer=TaxpayerInfo(
            name="Jordan Sample",
            ssn="000-00-0000",
            address="123 Demo Lane, Springfield, IL 62704",
        ),
        filing_status="single",
        digital_assets=False,
        refund_choice=RefundChoice(
            method="direct_deposit",
            routing_number="011000015",
            account_number="123456789",
            account_type="checking",
        ),
        w2=w2,
        summary=summary,
        output_dir=tmp_path,
    )

    assert generated_path.exists()
    assert generated_path.parent == tmp_path
    assert len(PdfReader(str(generated_path)).pages) >= 1

    text = extract_pdf_text(generated_path)
    assert "Jordan Sample" in text
    assert "000-00-0000" in text
    assert "Single" in text
    assert "Digital assets No" in text
    assert "Wages $40,000" in text
    assert "AGI $40,000" in text
    assert "Standard deduction $15,750" in text
    assert "Taxable income $24,250" in text
    assert "Tax $2,672" in text
    assert "Withholding $3,200" in text
    assert "Refund $528" in text
    assert "Direct deposit" in text
    assert "Routing 011000015" in text


def test_generate_1040_pdf_uses_env_output_dir_override(tmp_path, monkeypatch):
    env_output_dir = tmp_path / "generated-forms"
    monkeypatch.setenv("TAX_ASSISTANT_GENERATED_DIR", str(env_output_dir))
    w2 = make_w2(federal_income_tax_withheld=2_000)
    summary = calculate_tax_return(w2, "single")

    generated_path = generate_1040_pdf(
        taxpayer={"name": "Taylor Example", "ssn": "999-99-9999", "address": "9 Test Way, Austin, TX 78701"},
        filing_status="single",
        digital_assets=True,
        refund_choice={"method": "paper_check"},
        w2=w2,
        summary=summary,
    )

    assert generated_path.parent == env_output_dir
    assert generated_path.exists()

    text = extract_pdf_text(generated_path)
    assert "Taylor Example" in text
    assert "Digital assets Yes" in text
    assert "Amount owed $672" in text
    assert "Paper check" in text


def extract_pdf_text(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)
