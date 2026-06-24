from pathlib import Path
from typing import Union

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle, Paragraph


SAMPLE_W2_DATA = {
    "tax_year": 2025,
    "is_fake": True,
    "document_count": 1,
    "employee_name": "Jordan Sample",
    "employee_ssn": "000-00-0000",
    "employee_address": "123 Demo Lane, Springfield, IL 62704",
    "employer_name": "Example Payroll LLC",
    "employer_ein": "00-0000000",
    "employer_address": "456 Prototype Ave, Chicago, IL 60601",
    "box_1_wages": 40_000.00,
    "federal_income_tax_withheld": 3_200.00,
    "box_3_social_security_wages": 40_000.00,
    "social_security_tax_withheld": 2_480.00,
    "medicare_wages": 40_000.00,
    "medicare_tax_withheld": 580.00,
}


def create_sample_w2(output_path: Union[str, Path] = "assets/sample/sample-w2-2025.pdf") -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    rows = [
        ["SAMPLE FAKE W-2 - NOT FOR FILING", ""],
        ["Tax Year", str(SAMPLE_W2_DATA["tax_year"])],
        ["Fake Document", str(SAMPLE_W2_DATA["is_fake"])],
        ["Document Count", str(SAMPLE_W2_DATA["document_count"])],
        ["Employee Name", SAMPLE_W2_DATA["employee_name"]],
        ["Employee SSN", SAMPLE_W2_DATA["employee_ssn"]],
        ["Employee Address", SAMPLE_W2_DATA["employee_address"]],
        ["Employer Name", SAMPLE_W2_DATA["employer_name"]],
        ["Employer EIN", SAMPLE_W2_DATA["employer_ein"]],
        ["Employer Address", SAMPLE_W2_DATA["employer_address"]],
        ["Box 1 Wages, tips, other compensation", _money(SAMPLE_W2_DATA["box_1_wages"])],
        ["Box 2 Federal income tax withheld", _money(SAMPLE_W2_DATA["federal_income_tax_withheld"])],
        ["Box 3 Social Security wages", _money(SAMPLE_W2_DATA["box_3_social_security_wages"])],
        ["Box 4 Social Security tax withheld", _money(SAMPLE_W2_DATA["social_security_tax_withheld"])],
        ["Box 5 Medicare wages and tips", _money(SAMPLE_W2_DATA["medicare_wages"])],
        ["Box 6 Medicare tax withheld", _money(SAMPLE_W2_DATA["medicare_tax_withheld"])],
    ]

    table = Table(rows, colWidths=[3.4 * inch, 3.6 * inch])
    table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (1, 0)),
                ("BACKGROUND", (0, 0), (1, 0), colors.lightgrey),
                ("TEXTCOLOR", (0, 0), (1, 0), colors.red),
                ("FONTNAME", (0, 0), (1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (1, 0), "CENTER"),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.75, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    story = [
        Paragraph("2025 Wage and Tax Statement Demo", styles["Title"]),
        Spacer(1, 0.2 * inch),
        table,
    ]
    document.build(story)
    return path


def _money(value: float) -> str:
    return f"${value:,.2f}"


if __name__ == "__main__":
    create_sample_w2()
