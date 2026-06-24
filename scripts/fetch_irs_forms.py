from pathlib import Path
from typing import Optional, Union
from urllib.error import URLError
from urllib.request import urlopen
import shutil

import pdfplumber
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


IRS_FORM_1040_URL = "https://www.irs.gov/pub/irs-pdf/f1040.pdf"
FORM_1040_PATH = Path("assets/forms/f1040-2025.pdf")


def fetch_form_1040(
    output_path: Union[str, Path] = FORM_1040_PATH,
    source_path: Optional[Union[str, Path]] = None,
    url: str = IRS_FORM_1040_URL,
) -> Path:
    """Fetch or copy the 2025 Form 1040 base PDF.

    The IRS URL is intentionally only used when this function is called; importing
    this module never performs network I/O. If the official 2025 PDF is not
    available, the fallback prototype base is generated so the hackathon can keep
    producing readable 1040-style PDFs. Replace that fallback with the official
    IRS asset when it becomes available.
    """

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if source_path is not None:
        shutil.copyfile(Path(source_path), path)
        if _looks_like_2025_form_1040(path):
            return path
        _create_fallback_1040(path)
        return path

    try:
        with urlopen(url, timeout=20) as response:
            path.write_bytes(response.read())
        if _looks_like_2025_form_1040(path):
            return path
    except (OSError, URLError):
        pass

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


if __name__ == "__main__":
    fetch_form_1040()
