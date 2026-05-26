from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from server.core.parser.document import parse_pdf


def test_parse_pdf_real(tmp_path):
    p = tmp_path / "real.pdf"
    c = canvas.Canvas(str(p), pagesize=letter)
    c.drawString(100, 750, "Hello World Page1")
    c.showPage()
    c.drawString(100, 750, "Second Page Text")
    c.save()

    content, pages = parse_pdf(str(p))
    assert "Hello World Page1" in content
    assert "Second Page Text" in content
    assert len(pages) == 2
