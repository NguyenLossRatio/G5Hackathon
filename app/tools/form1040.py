from io import BytesIO
from pathlib import Path
from typing import Any, Mapping, Optional, Union
import os
import re

from pydantic import BaseModel
from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject, TextStringObject
from reportlab.pdfgen import canvas

from app.tools.tax_2025 import TaxReturnSummary
from app.tools.w2_parser import W2Data


REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_FORM_PATH = REPO_ROOT / "assets/forms/f1040-2025.pdf"
DEFAULT_GENERATED_DIR = REPO_ROOT / "var/generated"


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
    output_filename: Optional[str] = None,
) -> Path:
    taxpayer_info = _coerce_model(TaxpayerInfo, taxpayer)
    refund = _coerce_model(RefundChoice, refund_choice)
    base_path = BASE_FORM_PATH
    if not base_path.exists():
        raise FileNotFoundError(f"Form 1040 base PDF not found: {base_path}")

    destination_dir = _generated_dir(output_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    output_path = destination_dir / _output_filename(taxpayer_info.name, output_filename)

    writer = PdfWriter(clone_from=str(base_path))
    _set_need_appearances(writer)
    _fill_form_fields(writer, taxpayer_info, filing_status, digital_assets, refund, w2, summary)

    page1_overlay = _create_page1_overlay(
        writer.pages[0],
        taxpayer_info,
        filing_status,
        digital_assets,
        w2,
        summary,
    )
    writer.pages[0].merge_page(page1_overlay.pages[0])

    if len(writer.pages) > 1:
        page2_overlay = _create_page2_overlay(writer.pages[1], refund, summary)
        writer.pages[1].merge_page(page2_overlay.pages[0])

    with output_path.open("wb") as output_file:
        writer.write(output_file)

    return output_path


def _fill_form_fields(
    writer: PdfWriter,
    taxpayer: TaxpayerInfo,
    filing_status: str,
    digital_assets: bool,
    refund: RefundChoice,
    w2: Union[W2Data, Mapping[str, object]],
    summary: Union[TaxReturnSummary, Mapping[str, object]],
) -> None:
    field_values = {
        "f1_14[0]": taxpayer.name,
        "f1_16[0]": taxpayer.ssn,
        "f1_20[0]": taxpayer.address,
        "f1_47[0]": _money(_field(w2, "box_1_wages")),
        "f1_75[0]": _money(_field(summary, "agi")),
        "f2_01[0]": _money(_field(summary, "agi")),
        "f2_02[0]": _money(_field(summary, "standard_deduction")),
        "f2_06[0]": _money(_field(summary, "taxable_income")),
        "f2_08[0]": _money(_field(summary, "tax")),
        "f2_16[0]": _money(_field(summary, "tax")),
        "f2_17[0]": _money(_field(summary, "federal_withholding")),
        "f2_29[0]": _money(_field(summary, "federal_withholding")),
        "f2_30[0]": _money(_field(summary, "refund")),
        "f2_31[0]": _money(_field(summary, "refund")),
        "f2_35[0]": _money(_field(summary, "amount_owed")),
    }

    if _refund_method(refund) == "direct_deposit":
        field_values["f2_32[0]"] = refund.routing_number or ""
        field_values["f2_33[0]"] = refund.account_number or ""

    for page in writer.pages:
        for annot in _page_annotations(page):
            name = str(annot.get("/T") or "")
            if name in field_values:
                _set_text_annotation(annot, field_values[name])

    _check_box(writer.pages[0], *_filing_status_checkbox(filing_status))
    _check_box(writer.pages[0], "c1_10[0]" if digital_assets else "c1_10[1]")
    if _refund_method(refund) == "direct_deposit":
        account_type = (refund.account_type or "").strip().lower()
        if account_type == "checking":
            _check_box(writer.pages[1], "c2_16[0]")
        elif account_type == "savings":
            _check_box(writer.pages[1], "c2_16[1]")


def _set_need_appearances(writer: PdfWriter) -> None:
    if "/AcroForm" not in writer._root_object:
        return
    writer._root_object["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)


def _page_annotations(page: Any) -> list:
    annotations = []
    for annot_ref in page.get("/Annots") or []:
        annotations.append(annot_ref.get_object())
    return annotations


def _set_text_annotation(annot: Any, value: str) -> None:
    text = TextStringObject(str(value))
    annot[NameObject("/V")] = text
    annot[NameObject("/DV")] = text


def _check_box(page: Any, field_name: str, rect: Optional[tuple] = None) -> None:
    for annot in _page_annotations(page):
        if annot.get("/FT") != "/Btn":
            continue
        if str(annot.get("/T") or "") != field_name:
            continue
        if rect is not None and _rect_tuple(annot.get("/Rect")) != rect:
            continue
        state = _checked_state(annot)
        annot[NameObject("/V")] = NameObject(state)
        annot[NameObject("/AS")] = NameObject(state)
        return


def _checked_state(annot: Any) -> str:
    normal_appearance = (annot.get("/AP") or {}).get("/N")
    if hasattr(normal_appearance, "keys"):
        for state in normal_appearance.keys():
            state_name = str(state)
            if state_name != "/Off":
                return state_name
    return "/Yes"


def _filing_status_checkbox(filing_status: str) -> tuple:
    checkboxes = {
        "single": ("c1_8[0]", (97.599, 578.0, 105.599, 586.0)),
        "married_filing_jointly": ("c1_8[1]", (97.599, 566.001, 105.599, 574.001)),
        "married_filing_separately": ("c1_8[2]", (97.599, 554.002, 105.599, 562.002)),
        "head_of_household": ("c1_8[0]", (349.599, 578.0, 357.599, 586.0)),
    }
    return checkboxes[_normalize_status(filing_status)]


def _rect_tuple(rect: Any) -> tuple:
    return tuple(round(float(value), 3) for value in rect)


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
        c.setFont("Helvetica-Bold", 8)
        c.drawString(210, 764, f"Refund choice Direct deposit - Routing {refund.routing_number or ''}")
        c.setFont("Helvetica", 8)
        c.drawString(186, 274, refund.routing_number or "")
        c.drawString(186, 260, refund.account_number or "")
    else:
        c.setFont("Helvetica-Bold", 8)
        c.drawString(210, 764, "Refund choice Paper check")
        c.setFont("Helvetica", 8)
        c.drawString(74, 224, f"Amount owed {_money(_field(summary, 'amount_owed'))}")


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
        return Path(output_dir).expanduser().resolve()
    configured_dir = os.environ.get("TAX_ASSISTANT_GENERATED_DIR")
    if configured_dir:
        return Path(configured_dir).expanduser().resolve()
    return DEFAULT_GENERATED_DIR.resolve()


def _output_filename(taxpayer_name: str, output_filename: Optional[str]) -> str:
    if output_filename:
        name = Path(output_filename).name
        if Path(name).suffix.lower() != ".pdf":
            name = f"{name}.pdf"
        return name
    return f"completed-1040-2025-{_slug(taxpayer_name)}.pdf"


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


def _refund_method(refund: RefundChoice) -> str:
    return refund.method.strip().lower().replace(" ", "_")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or "taxpayer")[:80]
