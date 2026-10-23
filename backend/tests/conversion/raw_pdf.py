"""Hand-built PDFs for what reportlab does not write: a page tree that lies, odd content streams,
odd fonts. Each test builds the bytes it needs; none of them is checked in."""

HELVETICA = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
# Enough signs on a page for its text layer to count (app/conversion/text_layer.py)
SENTENCE = b"BT /F1 11 Tf 72 700 Td (Die Lernenden planen und pruefen ihre Arbeit sorgfaeltig.) Tj ET\n"


def pdf_of(objects: list[bytes]) -> bytes:
    """A PDF of these objects, numbered from 1 - the first is the catalog - with its cross-references."""
    out = bytearray(b"%PDF-1.7\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def stream(content: bytes) -> bytes:
    return b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream"


def pages_pdf(contents: list[bytes], *, count: int | None = None) -> bytes:
    """A PDF with an A4 page for each content stream, Helvetica as /F1; ``count``: the number of
    pages its page tree claims, where it should claim more than it holds."""
    kids = b" ".join(b"%d 0 R" % (4 + 2 * index) for index in range(len(contents)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(contents) if count is None else count),
        HELVETICA,
    ]
    for index, content in enumerate(contents):
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842]"
            b" /Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (5 + 2 * index)
        )
        objects.append(stream(content))
    return pdf_of(objects)
