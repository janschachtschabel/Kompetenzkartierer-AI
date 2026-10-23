"""Write the PDFs the conversion tests read (backend/tests/conversion/fixtures/).

reportlab is no dependency of the app: run this with any Python that has it and Pillow, for
instance the old app's environment. The files are invariant (no date, no random ID), so the same
reportlab writes the same bytes, and the tests read them as they are.

    python backend/tools/make_conversion_fixtures.py

What each file holds is what a test reads off it; change both together.
"""

import io
import sys
from collections.abc import Callable
from pathlib import Path

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

OUT = Path(__file__).resolve().parents[1] / "tests" / "conversion" / "fixtures"
WIDTH, HEIGHT = A4
LEFT = 20 * mm

BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=11, leading=14, spaceAfter=10)
HEADING = ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=14, leading=18, spaceAfter=8)
NOTE = ParagraphStyle("note", fontName="Helvetica-Oblique", fontSize=11, leading=14, spaceAfter=10)
CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=9, leading=11)
HEAD_CELL = ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=9, leading=11)

COMPETENCE = (
    "Die Schülerinnen und Schüler analysieren den Aufbau einer Steuerung und beschreiben die "
    "Funktion ihrer Baugruppen. Sie wählen geeignete Messmittel aus und dokumentieren ihre "
    "Ergebnisse in einem Prüfprotokoll."
)


def canvas_of(path: Path) -> Canvas:
    return Canvas(str(path), pagesize=A4, invariant=1, pageCompression=0)


def prose(path: Path) -> None:
    """Page 1: a bold heading, two paragraphs a gap apart, an italic note. Page 2: one paragraph."""
    document = SimpleDocTemplate(str(path), pagesize=A4, invariant=1, leftMargin=LEFT, topMargin=25 * mm)
    document.build(
        [
            Paragraph("1 Lernfeld Steuerungstechnik", HEADING),
            Paragraph(COMPETENCE, BODY),
            Paragraph("Sie bewerten Lösungen nach Kosten, Sicherheit und Wartbarkeit.", BODY),
            Paragraph("Hinweis: Die Inhalte sind verbindlich.", NOTE),
            Paragraph("2 Lernfeld Antriebe", HEADING),
            Paragraph(COMPETENCE.replace("Steuerung", "Antriebs"), BODY),
            Spacer(1, 520),
            Paragraph("Fortsetzung auf der zweiten Seite mit einem eigenen Absatz.", BODY),
        ]
    )


def edges(path: Path) -> None:
    """Five pages under the same running head; the footer prints I, II, then 1, 2, 3."""
    printed = ["I", "II", "1", "2", "3"]
    canvas = canvas_of(path)
    for number, label in enumerate(printed, start=1):
        canvas.setFont("Helvetica", 9)
        canvas.drawString(LEFT, HEIGHT - 12 * mm, "Rahmenlehrplan Mechatroniker und Mechatronikerin")
        canvas.setFont("Helvetica", 11)
        text = canvas.beginText(LEFT, HEIGHT - 40 * mm)
        text.textLine(f"Inhalt der Seite {number}: Lernfeld {number} beschreibt eine Aufgabe.")
        text.textLine("Die Auszubildenden planen und prüfen ihre Arbeit.")
        canvas.drawText(text)
        canvas.setFont("Helvetica", 9)
        canvas.drawCentredString(WIDTH / 2, 10 * mm, f"- {label} -")
        canvas.showPage()
    canvas.save()


def table(rows: list[list[str]], *, header: bool, widths: list[float]) -> LongTable:
    cells = [
        [Paragraph(text, HEAD_CELL if header and index == 0 else CELL) for text in row]
        for index, row in enumerate(rows)
    ]
    made = LongTable(cells, colWidths=widths, repeatRows=1 if header else 0)
    made.setStyle(
        TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP")])
    )
    return made


def tables(path: Path) -> None:
    """Page 1: a heading, a table with a bold header, text below it, then a long table without a
    header that runs onto page 2, text after it there; on page 3 a table with a header runs onto
    page 4 and repeats its header there."""
    widths = [30 * mm, 70 * mm, 60 * mm]
    plain = [
        [f"LF {n}", f"Ziel {n}: Die Lernenden planen Schritt {n}.", f"{n * 20} Stunden"] for n in range(1, 31)
    ]
    document = SimpleDocTemplate(str(path), pagesize=A4, invariant=1, leftMargin=LEFT, topMargin=25 * mm)
    document.build(
        [
            Paragraph("Übersicht über die Lernfelder", HEADING),
            table(
                [
                    ["Nr.", "Lernfeld", "Zeitrichtwert"],
                    ["1", "Einführung", "40 Stunden"],
                    ["2", "Planung", "60 Stunden"],
                ],
                header=True,
                widths=widths,
            ),
            Spacer(1, 12),
            Paragraph("Die Zeitrichtwerte gelten für das erste Ausbildungsjahr.", BODY),
            Spacer(1, 400),
            table(plain[:2] + plain[2:28], header=False, widths=widths),
            Paragraph("Text nach der ersten langen Tabelle.", BODY),
            Spacer(1, 360),
            table([["Nr.", "Lernfeld", "Zeitrichtwert"], *plain[:24]], header=True, widths=widths),
        ]
    )


def scan(path: Path) -> None:
    """Three pages of an image and no text, one page of text: a scan with a typed cover note."""
    picture = Image.new("RGB", (400, 560), "white")
    for x in range(40, 360, 8):
        for y in range(60, 500, 24):
            picture.putpixel((x, y), (0, 0, 0))
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    canvas = canvas_of(path)
    canvas.setFont("Helvetica", 11)
    canvas.drawString(LEFT, HEIGHT - 40 * mm, "Eingescannter Lehrplan, Deckblatt mit Text auf dieser Seite.")
    canvas.showPage()
    for _ in range(3):
        buffer.seek(0)
        canvas.drawImage(ImageReader(buffer), LEFT, 40 * mm, width=WIDTH - 2 * LEFT, height=HEIGHT - 80 * mm)
        canvas.showPage()
    canvas.save()


FIXTURES: dict[str, Callable[[Path], None]] = {
    "prose.pdf": prose,
    "edges.pdf": edges,
    "tables.pdf": tables,
    "scan.pdf": scan,
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, write in FIXTURES.items():
        write(OUT / name)
        print(f"{name}: {(OUT / name).stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
