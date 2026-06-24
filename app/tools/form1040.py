from io import BytesIO
from pathlib import Path
from typing import Any, Mapping, Optional, Union
import os
import re

from pydantic import BaseModel
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from app.tools.tax_2025 import TaxReturnSummary
from app.tools.w2_parser import W2Data


BASE_FORM_PATH = Path("assets/forms/f1040-2025.pdf")
DEFAULT_GENERATED_DIR = Path("var/generated")


class TaxpayerInfo(BaseModel):
    name: str
    ssn: str
    address: str


class RefundChoice(BaseModel):
    method: str = "paper_check"
    routing_number: Optional[str] = None
    account_number: Optional[str] = None
    account_type: Optional[str] = None


def generate_1040_pdf(
    taxpayer: Union[TaxpayerInfo, Mapping[str, object]],
    filing_status: str,
    digital_assets: bool,
    refund_choice: Union[RefundChoice, Mapping[str, object]],
    w2: Union[W2Data, Mapping[str, object]],
    summary: Union[TaxReturnSummary, Mapping[str, object]],
    output_dir: Optional[Union[str, Path]] = None,
) -> Path:
    taxpayer_info = _coerce_model(TaxpayerInfo, taxpayer)
    refund = _coerce_model(RefundChoice, refund_choice)
    base_path = BASE_FORM_PATH
    if not base_path.exists():
        raise FileNotFoundError(f"Form 1040 base PDF not found: {base_path}")

    destination_dir = _generated_dir(output_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    output_path = destination_dir / f"completed-1040-2025-{_slug(taxpayer_info.name)}.pdf"

    reader = PdfReader(str(base_path))
    writer = PdfWriter()

    page1_overlay = _create_page1_overlay(
        reader.pages[0],
        taxpayer_info,
        filing_status,
        digital_assets,
        w2,
        summary,
    )
    writer.add_page(reader.pages[0])
    writer.pages[0].merge_page(page1_overlay.pages[0])

    if len(reader.pages) > 1:
        page2_overlay = _create_page2_overlay(reader.pages[1], refund, summary)
        writer.add_page(reader.pages[1])
        writer.pages[1].merge_page(page2_overlay.pages[0])

    for page in reader.pages[2:]:
        writer.add_page(page)

    summary_page = _create_extractable_summary_page(taxpayer_info, filing_status, digital_assets, refund, w2, summary)
    writer.add_page(summary_page.pages[0])

    with output_path.open("wb") as output_file:
        writer.write(output_file)

    return output_path


def _create_page1_overlay(
    base_page: Any,
    taxpayer: TaxpayerInfo,
    filing_status: str,
    digital_assets: bool,
    w2: Union[W2Data, Mapping[str, object]],
    summary: Union[TaxReturnSummary, Mapping[str, object]],
) -> PdfReader:
    width = float(base_page.mediabox.width)
    height = float(base_page.mediabox.height)
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(width, height))

    _draw_header_values(c, taxpayer, filing_status, digital_assets)
    _draw_page1_money_values(c, w2, summary)
    _draw_status_marks(c, filing_status, digital_assets)
    c.save()

    packet.seek(0)
    return PdfReader(packet)


def _create_page2_overlay(
    base_page: Any,
    refund: RefundChoice,
    summary: Union[TaxReturnSummary, Mapping[str, object]],
) -> PdfReader:
    width = float(base_page.mediabox.width)
    height = float(base_page.mediabox.height)
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(width, height))

    _draw_page2_money_values(c, refund, summary)
    c.save()

    packet.seek(0)
    return PdfReader(packet)


def _create_extractable_summary_page(
    taxpayer: TaxpayerInfo,
    filing_status: str,
    digital_assets: bool,
    refund: RefundChoice,
    w2: Union[W2Data, Mapping[str, object]],
    summary: Union[TaxReturnSummary, Mapping[str, object]],
) -> PdfReader:
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(612, 792))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 742, "Completed 2025 Form 1040 Values")
    c.setFont("Helvetica", 11)

    lines = _completed_value_lines(taxpayer, filing_status, digital_assets, refund, w2, summary)
    y = 710
    for line in lines:
        c.drawString(50, y, line)
        y -= 22

    c.save()
    packet.seek(0)
    return PdfReader(packet)


def _draw_header_values(
    c: canvas.Canvas,
    taxpayer: TaxpayerInfo,
    filing_status: str,
    digital_assets: bool,
) -> None:
    c.setFont("Helvetica", 8)
    for x, y, line in [
        (94, 679, taxpayer.name),
        (458, 679, taxpayer.ssn),
        (94, 632, taxpayer.address),
        (392, 493, "Digital assets " + ("Yes" if digital_assets else "No")),
    ]:
        c.drawString(x, y, line)


def _draw_page1_money_values(
    c: canvas.Canvas,
    w2: Union[W2Data, Mapping[str, object]],
    summary: Union[TaxReturnSummary, Mapping[str, object]],
) -> None:
    c.setFont("Helvetica", 8)
    c.drawRightString(596, 333, _money(_field(w2, "box_1_wages")))
    c.drawRightString(596, 30, _money(_field(summary, "agi")))


def _draw_page2_money_values(
    c: canvas.Canvas,
    refund: RefundChoice,
    summary: Union[TaxReturnSummary, Mapping[str, object]],
) -> None:
    c.setFont("Helvetica", 8)
    c.drawRightString(596, 747, _money(_field(summary, "agi")))
    c.drawRightString(596, 686, _money(_field(summary, "standard_deduction")))
    c.drawRightString(596, 638, _money(_field(summary, "taxable_income")))
    c.drawRightString(596, 626, _money(_field(summary, "tax")))
    c.drawRightString(596, 530, _money(_field(summary, "tax")))
    c.drawRightString(596, 503, _money(_field(summary, "federal_withholding")))
    c.drawRightString(596, 312, _money(_field(summary, "federal_withholding")))
    c.drawRightString(596, 300, _money(_field(summary, "refund")))
    c.drawRightString(596, 286, _money(_field(summary, "refund")))
    c.drawRightString(596, 224, _money(_field(summary, "amount_owed")))

    if _refund_method(refund) == "direct_deposit":
        c.drawString(186, 274, refund.routing_number or "")
        c.drawString(186, 260, refund.account_number or "")
        if (refund.account_type or "").strip().lower() == "checking":
            _draw_check(c, 392, 273)
        elif (refund.account_type or "").strip().lower() == "savings":
            _draw_check(c, 452, 273)


def _completed_value_lines(
    taxpayer: TaxpayerInfo,
    filing_status: str,
    digital_assets: bool,
    refund: RefundChoice,
    w2: Union[W2Data, Mapping[str, object]],
    summary: Union[TaxReturnSummary, Mapping[str, object]],
) -> list:
    lines = [
        f"Taxpayer {taxpayer.name}",
        f"SSN {taxpayer.ssn}",
        f"Address {taxpayer.address}",
        f"Filing status {_status_label(filing_status)}",
        f"Digital assets {'Yes' if digital_assets else 'No'}",
        f"Wages {_money(_field(summary, 'wages'))}",
        f"AGI {_money(_field(summary, 'agi'))}",
        f"Standard deduction {_money(_field(summary, 'standard_deduction'))}",
        f"Taxable income {_money(_field(summary, 'taxable_income'))}",
        f"Tax {_money(_field(summary, 'tax'))}",
        f"Withholding {_money(_field(summary, 'federal_withholding'))}",
        f"Refund {_money(_field(summary, 'refund'))}",
        f"Amount owed {_money(_field(summary, 'amount_owed'))}",
        f"W-2 Box 1 {_money(_field(w2, 'box_1_wages'))}",
        f"W-2 Box 2 {_money(_field(w2, 'federal_income_tax_withheld'))}",
    ]

    if _refund_method(refund) == "direct_deposit":
        lines.extend(
            [
                "Refund delivery Direct deposit",
                f"Routing {refund.routing_number or ''}",
                f"Account {refund.account_number or ''}",
                f"Type {_account_type_label(refund.account_type)}",
            ]
        )
    else:
        lines.append("Refund delivery Paper check")

    return lines


def _draw_status_marks(c: canvas.Canvas, filing_status: str, digital_assets: bool) -> None:
    status_positions = {
        "single": (99, 584),
        "married_filing_jointly": (99, 572),
        "married_filing_separately": (99, 559),
        "head_of_household": (361, 584),
    }
    normalized_status = _normalize_status(filing_status)
    status_position = status_positions.get(normalized_status)
    if status_position is not None:
        _draw_check(c, *status_position)

    _draw_check(c, 522 if digital_assets else 565, 491)


def _draw_check(c: canvas.Canvas, x: float, y: float) -> None:
    c.setLineWidth(1.2)
    c.line(x, y, x + 4, y - 5)
    c.line(x + 4, y - 5, x + 12, y + 7)


def _generated_dir(output_dir: Optional[Union[str, Path]]) -> Path:
    if output_dir is not None:
        return Path(output_dir)
    return Path(os.environ.get("TAX_ASSISTANT_GENERATED_DIR", DEFAULT_GENERATED_DIR))


def _coerce_model(model: Any, value: Union[BaseModel, Mapping[str, object]]) -> Any:
    if isinstance(value, model):
        return value
    if hasattr(model, "model_validate"):
        return model.model_validate(value)
    return model.parse_obj(value)


def _field(source: Union[BaseModel, Mapping[str, object]], name: str) -> object:
    if isinstance(source, Mapping):
        return source[name]
    return getattr(source, name)


def _money(value: object) -> str:
    return f"${float(value):,.0f}"


def _normalize_status(status: str) -> str:
    return status.strip().lower().replace(" ", "_")


def _status_label(status: str) -> str:
    labels = {
        "single": "Single",
        "married_filing_jointly": "Married filing jointly",
        "married_filing_separately": "Married filing separately",
        "head_of_household": "Head of household",
    }
    return labels.get(_normalize_status(status), status)


def _refund_method(refund: RefundChoice) -> str:
    return refund.method.strip().lower().replace(" ", "_")


def _account_type_label(account_type: Optional[str]) -> str:
    if not account_type:
        return ""
    return account_type.strip().title()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "taxpayer"
