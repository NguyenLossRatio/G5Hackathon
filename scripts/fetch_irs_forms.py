from pathlib import Path
from typing import Optional, Union
from urllib.error import URLError
from urllib.request import urlopen
import argparse
import shutil

import pdfplumber
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


IRS_FORM_1040_URL = "https://www.irs.gov/pub/irs-pdf/f1040.pdf"
REPO_ROOT = Path(__file__).resolve().parents[1]
FORM_1040_PATH = REPO_ROOT / "assets/forms/f1040-2025.pdf"


def fetch_form_1040(
    output_path: Union[str, Path] = FORM_1040_PATH,
    source_path: Optional[Union[str, Path]] = None,
    url: str = IRS_FORM_1040_URL,
    allow_prototype: bool = False,
) -> Path:
    """Fetch or copy the 2025 Form 1040 base PDF.

    The IRS URL is intentionally only used when this function is called; importing
    this module never performs network I/O. Prototype fallback generation is
    explicit: pass allow_prototype=True only for local hackathon development when
    the official IRS 2025 asset is unavailable. Replace that fallback with the
    official IRS asset before committing production assets.
    """

    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    if source_path is not None:
        source = Path(source_path).expanduser().resolve()
        if _looks_like_2025_form_1040(source):
            shutil.copyfile(source, path)
            return path
        return _handle_unavailable_form(path, allow_prototype)

    downloaded_path = path.with_name(f"{path.name}.download")
    try:
        with urlopen(url, timeout=20) as response:
            downloaded_path.write_bytes(response.read())
        if _looks_like_2025_form_1040(downloaded_path):
            downloaded_path.replace(path)
            return path
    except (OSError, URLError):
        pass
    finally:
        if downloaded_path.exists():
            downloaded_path.unlink()

    return _handle_unavailable_form(path, allow_prototype)


def _handle_unavailable_form(path: Path, allow_prototype: bool) -> Path:
    if not allow_prototype:
        raise RuntimeError(
            "Official 2025 Form 1040 PDF was not available. "
            "Pass allow_prototype=True to create the prototype fallback explicitly."
        )

    _create_fallback_1040(path)
    return path


def _looks_like_2025_form_1040(path: Path) -> bool:
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                return False
            text = pdf.pages[0].extract_text() or ""
    except Exception:
        return False

    return "1040" in text and "2025" in text and "U.S. Individual Income Tax Return" in text


def _create_fallback_1040(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 18)
    c.drawString(0.6 * inch, height - 0.65 * inch, "2025 Form 1040 Prototype Base")
    c.setFont("Helvetica", 10)
    c.drawString(0.6 * inch, height - 0.9 * inch, "U.S. Individual Income Tax Return - Hackathon Prototype")
    c.setStrokeColor(colors.black)
    c.line(0.6 * inch, height - 1.0 * inch, width - 0.6 * inch, height - 1.0 * inch)

    sections = [
        ("Taxpayer", 9.55),
        ("Filing Status", 8.55),
        ("Digital Assets", 7.85),
        ("Income and Tax", 7.15),
        ("Payments", 5.65),
        ("Refund or Amount Owed", 4.6),
    ]
    c.setFont("Helvetica-Bold", 11)
    for label, y_inch in sections:
        y = y_inch * inch
        c.drawString(0.65 * inch, y, label)
        c.rect(0.6 * inch, y - 0.55 * inch, width - 1.2 * inch, 0.45 * inch)

    c.setFont("Helvetica", 8)
    c.drawString(
        0.6 * inch,
        0.55 * inch,
        "Prototype base only. Replace with the official IRS 2025 Form 1040 PDF before real filing workflows.",
    )
    c.showPage()
    c.save()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch the IRS 2025 Form 1040 PDF asset.")
    parser.add_argument("--output", default=str(FORM_1040_PATH), help="Destination PDF path.")
    parser.add_argument("--source", help="Local PDF to validate and copy instead of downloading.")
    parser.add_argument("--url", default=IRS_FORM_1040_URL, help="IRS PDF URL.")
    parser.add_argument(
        "--allow-prototype",
        action="store_true",
        help="Create a visible prototype fallback if the official 2025 form is unavailable.",
    )
    args = parser.parse_args()
    fetch_form_1040(
        output_path=args.output,
        source_path=args.source,
        url=args.url,
        allow_prototype=args.allow_prototype,
    )


if __name__ == "__main__":
    main()
