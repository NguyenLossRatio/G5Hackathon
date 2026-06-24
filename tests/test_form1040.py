from pathlib import Path

import pdfplumber
from pypdf import PdfReader

from app.tools.form1040 import BASE_FORM_PATH, RefundChoice, TaxpayerInfo, generate_1040_pdf
from app.tools.tax_2025 import calculate_tax_return
from app.tools.w2_parser import W2Data
from scripts.fetch_irs_forms import fetch_form_1040


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
            routing_number="000000000",
            account_number="000000000000",
            account_type="checking",
        ),
        w2=w2,
        summary=summary,
        output_dir=tmp_path,
    )

    assert generated_path.exists()
    assert generated_path.parent == tmp_path.resolve()
    reader = PdfReader(str(generated_path))
    assert len(reader.pages) == 2

    text = extract_pdf_text(generated_path)
    assert "Jordan Sample" in text
    assert "000-00-0000" in text
    assert "123 Demo Lane, Springfield, IL 62704" in text
    assert "Digital assets No" in text
    assert "Direct deposit" in text
    assert "Routing 000000000" in text

    fields = form_field_values(reader)
    assert fields["topmostSubform[0].Page1[0].f1_14[0]"] == "Jordan Sample"
    assert fields["topmostSubform[0].Page1[0].f1_16[0]"] == "000-00-0000"
    assert fields["topmostSubform[0].Page1[0].Address_ReadOrder[0].f1_20[0]"] == (
        "123 Demo Lane, Springfield, IL 62704"
    )
    assert fields["topmostSubform[0].Page1[0].f1_47[0]"] == "$40,000"
    assert fields["topmostSubform[0].Page1[0].f1_75[0]"] == "$40,000"
    assert fields["topmostSubform[0].Page2[0].f2_01[0]"] == "$40,000"
    assert fields["topmostSubform[0].Page2[0].f2_02[0]"] == "$15,750"
    assert fields["topmostSubform[0].Page2[0].f2_06[0]"] == "$24,250"
    assert fields["topmostSubform[0].Page2[0].f2_08[0]"] == "$2,672"
    assert fields["topmostSubform[0].Page2[0].f2_17[0]"] == "$3,200"
    assert fields["topmostSubform[0].Page2[0].f2_29[0]"] == "$3,200"
    assert fields["topmostSubform[0].Page2[0].f2_31[0]"] == "$528"
    assert fields["topmostSubform[0].Page2[0].RoutingNo[0].f2_32[0]"] == "000000000"
    assert fields["topmostSubform[0].Page2[0].AccountNo[0].f2_33[0]"] == "000000000000"
    checked = checked_annotation_rects(reader)
    assert (1, "c1_8[0]", (97.599, 578.0, 105.599, 586.0)) in checked
    assert (1, "c1_10[1]", (554.4, 497.0, 562.4, 505.0)) in checked
    assert (2, "c2_16[0]", (377.4, 278.001, 385.4, 286.001)) in checked


def test_generate_1040_pdf_uses_env_output_dir_override(tmp_path, monkeypatch):
    env_output_dir = tmp_path / "generated-forms"
    monkeypatch.setenv("TAX_ASSISTANT_GENERATED_DIR", str(env_output_dir))
    w2 = make_w2(federal_income_tax_withheld=2_000)
    summary = calculate_tax_return(w2, "single")

    generated_path = generate_1040_pdf(
        taxpayer={"name": "Taylor ../Example?*", "ssn": "999-99-9999", "address": "9 Test Way, Austin, TX 78701"},
        filing_status="single",
        digital_assets=True,
        refund_choice={"method": "paper_check"},
        w2=w2,
        summary=summary,
    )

    assert generated_path.parent == env_output_dir
    assert generated_path.name == "completed-1040-2025-taylor-example.pdf"
    assert generated_path.exists()
    assert len(PdfReader(str(generated_path)).pages) == 2

    text = extract_pdf_text(generated_path)
    assert "Taylor ../Example?*" in text
    assert "Digital assets Yes" in text
    assert "Amount owed $672" in text
    assert "Paper check" in text


def test_generate_1040_pdf_is_anchored_to_repo_root_when_called_from_different_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    w2 = make_w2()
    summary = calculate_tax_return(w2, "single")

    generated_path = generate_1040_pdf(
        taxpayer=TaxpayerInfo(
            name="Casey Cwd",
            ssn="111-11-1111",
            address="1 Different Cwd, Madison, WI 53703",
        ),
        filing_status="single",
        digital_assets=False,
        refund_choice={"method": "paper_check"},
        w2=w2,
        summary=summary,
        output_dir=tmp_path / "out",
    )

    assert generated_path.exists()
    assert len(PdfReader(str(generated_path)).pages) == 2
    assert "Casey Cwd" in extract_pdf_text(generated_path)


def test_committed_form1040_asset_is_official_2025_two_page_form_with_expected_fields():
    reader = PdfReader(str(BASE_FORM_PATH))
    text = extract_pdf_text(BASE_FORM_PATH)
    fields = reader.get_fields() or {}

    assert len(reader.pages) == 2
    assert "Form 1040" in text
    assert "2025" in text
    assert "U.S. Individual Income Tax Return" in text
    assert "2025 Form 1040 Prototype Base" not in text
    assert "topmostSubform[0].Page1[0].f1_14[0]" in fields
    assert "topmostSubform[0].Page1[0].c1_10[0]" in fields
    assert "topmostSubform[0].Page2[0].RoutingNo[0].f2_32[0]" in fields
    assert "topmostSubform[0].Page2[0].AccountNo[0].f2_33[0]" in fields


def test_fetch_form_1040_requires_explicit_prototype_fallback(tmp_path):
    output_path = tmp_path / "form.pdf"

    try:
        fetch_form_1040(output_path=output_path, url="file:///missing-form.pdf")
    except RuntimeError as exc:
        assert "allow_prototype=True" in str(exc)
    else:
        raise AssertionError("fetch_form_1040 should reject fallback unless explicitly allowed")

    assert not output_path.exists()


def extract_pdf_text(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def form_field_values(reader: PdfReader):
    fields = reader.get_fields() or {}
    return {name: str(field.get("/V")) for name, field in fields.items() if field.get("/V") is not None}


def checked_annotation_rects(reader: PdfReader):
    checked = set()
    for page_index, page in enumerate(reader.pages, start=1):
        for annot_ref in page.get("/Annots") or []:
            annot = annot_ref.get_object()
            if annot.get("/FT") != "/Btn":
                continue
            if str(annot.get("/V")) == "/Off" and str(annot.get("/AS")) == "/Off":
                continue
            rect = tuple(round(float(value), 3) for value in annot.get("/Rect"))
            checked.add((page_index, str(annot.get("/T")), rect))
    return checked
