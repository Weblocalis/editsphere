"""Tests hors ligne de clean_kdp.py — lancer avec : python3 -m pytest -q"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import clean_kdp  # noqa: E402

BOOKS = ROOT / "victor-hugo"


def book(name):
    return clean_kdp.clean_book(BOOKS / name)


def test_url_pattern_keeps_sentences():
    # L'ancienne version effaçait « cherchait. De » en le prenant pour un nom de domaine.
    text = "Il cherchait. De loin, il vit www.exemple.com et http://a.fr/x puis Paris. Co"
    cleaned = clean_kdp.URL_RE.sub("", text)
    assert "cherchait. De loin" in cleaned and "Paris. Co" in cleaned
    assert "www" not in cleaned and "http" not in cleaned


def test_french_spacing():
    assert clean_kdp.french_spacing("Quoi ? « Oui » ; non !") == \
        "Quoi ? « Oui » ; non !"


def test_kdp_gutter_table():
    assert clean_kdp.kdp_min_gutter(100) == 0.375
    assert clean_kdp.kdp_min_gutter(301) == 0.625
    assert clean_kdp.kdp_min_gutter(828) == 0.875


def test_word_book_is_cleaned_without_losing_text():
    b = book("CLAUDE GUEUX.html")
    assert (b.title, b.author, b.year) == ("CLAUDE GUEUX", "Victor Hugo", "1834")
    assert b.words_match, b.warnings
    assert b.notes_kept == 3
    for residue in ("Mso", "ebooksgratuits", "Ebooks libres", "http", "style=", "<a ", "<span>"):
        assert residue not in b.body
    assert not [w for w in b.warnings if w.startswith("Reste")]


def test_mhtml_archive_is_read():
    b = book("napoleon-le-petit.html")
    assert b.title == "NAPOLÉON LE PETIT" and b.year == "1852"
    assert b.words_match
    assert b.notes_removed == 16  # notes « ELG » du correcteur, pas de Hugo


def test_modern_annotations_are_removed():
    b = book("Les Misérables - Tome I - Fantine.html")
    assert b.notes_kept == 0 and b.notes_removed == 188
    assert "Guy Rosa" not in b.body
    assert "[1]" not in b.body
    assert b.subtitle == "Tome I – FANTINE"


def test_untitled_preface_is_kept():
    b = book("LE ROI S’AMUSE.html")
    assert "Il est profondément triste" in b.body
    assert "Ebooks" not in b.body


def test_verse_is_detected():
    b = book("les-contemplations.html")
    assert b.verse_lines > 10000
    assert b.words_match


def test_pdf_has_kdp_trim_size(tmp_path):
    pytest.importorskip("weasyprint")
    b = book("CLAUDE GUEUX.html")
    layout = clean_kdp.Layout(width=5.5, height=8.5)
    pdf = tmp_path / "cg.pdf"
    pages, layout = clean_kdp.render_pdf(b, layout, pdf, lambda _msg: None)
    assert 24 <= pages <= clean_kdp.KDP_MAX_PAGES
    assert layout.inside >= clean_kdp.kdp_min_gutter(pages)
    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(pdf)
    assert len(reader.pages) == pages
    for page in reader.pages:
        box = page.mediabox
        assert (round(float(box.width)), round(float(box.height))) == (396, 612)  # 5,5 x 8,5 po
    fonts = set()
    for page in reader.pages[:6]:
        for font in (page["/Resources"].get("/Font") or {}).values():
            font = font.get_object()
            fonts.add(str(font["/BaseFont"]))
            descendant = font.get("/DescendantFonts")
            if descendant:
                descriptor = descendant[0].get_object()["/FontDescriptor"].get_object()
                assert "/FontFile2" in descriptor or "/FontFile3" in descriptor  # incorporée
    assert any("Garamond" in name for name in fonts), fonts
