import sys
import pdfplumber
from types import SimpleNamespace
from server.core.parser.document import parse_pdf, parse_image


def test_parse_pdf_monkeypatch(monkeypatch, tmp_path):
    class P:
        def __init__(self, text):
            self._text = text
        def extract_text(self):
            return self._text

    class FakePDF:
        def __init__(self, pages):
            self.pages = pages
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    # monkeypatch pdfplumber.open to return fake pdf with pages
    monkeypatch.setattr(pdfplumber, 'open', lambda fp: FakePDF([P("Page1 text"), P("")]))

    content, pages = parse_pdf(str(tmp_path / "a.pdf"))
    assert "Page1 text" in content
    assert isinstance(pages, list) and pages[0]['page'] == 1


def test_parse_image_rapidocr_then_pytesseract(monkeypatch, tmp_path):
    p = tmp_path / 'img.png'
    p.write_bytes(b'')

    # Simulate rapidocr available
    class RapidOut:
        def __init__(self, txts):
            self.txts = txts

    class RapidOCR:
        def __call__(self, fp):
            return RapidOut(['r1', 'r2'])

    monkeypatch.setitem(sys.modules, 'rapidocr', SimpleNamespace(RapidOCR=RapidOCR))

    content, paras = parse_image(str(p))
    assert 'r1' in content
    assert len(paras) == 2

    # Force rapidocr to fail at construction so code falls back to pytesseract
    class RapidOCRFail:
        def __init__(self):
            raise Exception("simulate rapidocr failure")
    monkeypatch.setitem(sys.modules, 'rapidocr', SimpleNamespace(RapidOCR=RapidOCRFail))

    def fake_image_open(fp):
        return SimpleNamespace(mode='RGB', convert=lambda m: SimpleNamespace())

    monkeypatch.setitem(sys.modules, 'pytesseract', SimpleNamespace(image_to_string=lambda img, lang=None: "pt1\npt2"))
    # Provide a fake PIL module with Image.open
    monkeypatch.setitem(sys.modules, 'PIL', SimpleNamespace(Image=SimpleNamespace(open=fake_image_open)))

    content2, paras2 = parse_image(str(p))
    assert 'pt1' in content2
    assert len(paras2) == 2
