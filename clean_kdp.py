#!/usr/bin/env python3
"""EditSphere — nettoie des livres du domaine public et produit un intérieur
broché prêt pour Amazon KDP (PDF au format exact, polices incorporées,
marges miroir, titres courants, folios, notes en bas de page, table des
matières).

Usage le plus simple (traite tout le dossier ``victor-hugo/``)::

    python3 clean_kdp.py

Un seul livre, format 5,5 x 8,5 pouces::

    python3 clean_kdp.py "victor-hugo/CLAUDE GUEUX.html" --format 5.5x8.5

Les fichiers d'origine ne sont jamais modifiés. Pour chaque livre, le dossier
de sortie contient le HTML nettoyé, le PDF intérieur et un rapport.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
import time
import unicodedata
import urllib.parse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from pathlib import Path

try:
    from bs4 import BeautifulSoup, Comment, NavigableString, Tag
except ImportError:  # pragma: no cover - message for end users
    sys.exit("Module manquant : installez les dépendances avec\n"
             "    pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parent
FONTS_DIR = ROOT / "fonts"

# ---------------------------------------------------------------------------
# Paramètres KDP
# ---------------------------------------------------------------------------

# Formats de livre broché proposés par KDP (largeur, hauteur en pouces).
TRIM_SIZES = {
    "5x8": (5.0, 8.0),
    "5.06x7.81": (5.06, 7.81),
    "5.25x8": (5.25, 8.0),
    "5.5x8.5": (5.5, 8.5),
    "6x9": (6.0, 9.0),
    "6.14x9.21": (6.14, 9.21),
    "6.69x9.61": (6.69, 9.61),
    "7x10": (7.0, 10.0),
}

# Marge intérieure (petit fond) minimale exigée par KDP selon le nombre de pages.
KDP_GUTTER = [(150, 0.375), (300, 0.5), (500, 0.625), (700, 0.75), (828, 0.875)]
KDP_MIN_PAGES = 24
KDP_MAX_PAGES = 828
GUTTER_COMFORT = 0.25   # pouces ajoutés au minimum KDP pour le confort de lecture
OUTSIDE_MARGIN = 0.55   # grand fond
TOP_MARGIN = 0.8        # le titre courant est placé dans cette marge
BOTTOM_MARGIN = 0.75    # le folio est placé dans cette marge


SOURCE_SUFFIXES = (".html", ".htm", ".mhtml", ".mht")


def kdp_min_gutter(pages: int) -> float:
    for limit, gutter in KDP_GUTTER:
        if pages <= limit:
            return gutter
    return KDP_GUTTER[-1][1]


# ---------------------------------------------------------------------------
# Lecture des sources (HTML Word, HTML web, archive MHTML « Saved by Blink »)
# ---------------------------------------------------------------------------

def decode_html(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    head = data[:4096].decode("ascii", errors="ignore")
    match = re.search(r"charset\s*=\s*[\"']?([\w-]+)", head, re.I)
    declared = match.group(1).lower() if match else None
    candidates = ["utf-8"] + ([declared] if declared and declared != "utf-8" else []) + ["cp1252"]
    for encoding in candidates:
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def load_source(path: Path) -> str:
    raw = path.read_bytes()
    if not raw.lstrip().startswith(b"From: <Saved by Blink>"):
        return decode_html(raw)
    # Certaines sauvegardes MHTML ont des en-têtes MIME indentés : on les remet en colonne 0.
    raw = re.sub(
        rb"(?m)^[ \t]+(?=(?:From:|Snapshot-Content-Location:|Subject:|Date:|"
        rb"MIME-Version:|Content-Type:|Content-ID:|Content-Transfer-Encoding:|"
        rb"Content-Location:|[-]{2,}MultipartBoundary))",
        b"", raw)
    message = BytesParser(policy=policy.default).parsebytes(raw)
    part = next((p for p in message.walk() if p.get_content_type() == "text/html"), None)
    if part is None:
        raise ValueError("archive MHTML sans partie text/html")
    payload = part.get_payload(decode=True) or b""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset)
    except (UnicodeDecodeError, LookupError):
        return decode_html(payload)


# ---------------------------------------------------------------------------
# Outils texte
# ---------------------------------------------------------------------------

def normalize_words(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", " ", plain).strip()


def text_of(node: Tag) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ").replace("\xa0", " ")).strip()


WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def words(text: str) -> list[str]:
    return WORD_RE.findall(text)


URL_RE = re.compile(r"(?i)\b(?:https?://|ftp://|www\.)[^\s<>«»\"]+")
YEAR_RE = re.compile(r"\b(1[4-9]\d\d)\b")
EDITOR_NOTE_RE = re.compile(
    r"(?i)note du correcteur|note de l[’']éditeur|n\.\s?d\.\s?[ée]\.|\bELG\b|ebooks libres")
ANNOTATED_RE = re.compile(r"(?i)texte annoté par|annoté par|annotations? de")
PUBLISHER_RE = re.compile(r"(?i)ebooks?\s*libres\s*et\s*gratuits|ebooksgratuits|"
                          r"publication par le groupe|publication du groupe")

BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "table", "ul", "ol"}
INLINE_KEEP = {"i", "em", "b", "strong", "sup", "sub", "small", "br", "u", "s", "img"}
STRUCT_KEEP = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "table", "thead",
               "tbody", "tfoot", "tr", "td", "th", "ul", "ol", "li", "dl", "dt", "dd"}
DROP_TAGS = ["script", "style", "noscript", "svg", "iframe", "object", "embed",
             "form", "input", "button", "select", "textarea", "video", "audio", "canvas",
             "map", "area", "link", "meta", "base", "title", "head", "hr", "nav"]
TOC_HEADINGS = {"table des matieres", "sommaire", "table of contents", "contents", "table"}
ABOUT_HEADING = "a propos de cette edition electronique"


# ---------------------------------------------------------------------------
# Nettoyage
# ---------------------------------------------------------------------------

@dataclass
class Book:
    source: Path
    title: str = ""
    subtitle: str = ""
    author: str = ""
    year: str = ""
    body: str = ""
    headings: list[tuple[int, str, str]] = field(default_factory=list)  # (niveau, id, texte)
    report: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    words_source: int = 0
    words_output: int = 0
    words_match: bool = False
    notes_kept: int = 0
    notes_removed: int = 0
    verse_lines: int = 0
    images_kept: int = 0
    low_res: list[str] = field(default_factory=list)
    image_files: dict[str, Path] = field(default_factory=dict)  # images à copier à côté du HTML


def _remove_after(node: Tag) -> None:
    """Supprime ``node`` et tout ce qui le suit dans l'ordre du document."""
    current = node
    while current is not None and current.name not in ("body", "html", "[document]"):
        for sibling in list(current.next_siblings):
            sibling.extract()
        current = current.parent
    node.extract()


TITLE_CLASSES = {"auteur", "titrelivre", "datesortie", "book-author", "book-title", "book-year"}
FRONT_RE = re.compile(r"(?i)texte établi|première publication|annoté par|^\(?\d{4}\)?$")


def strip_front_matter(body: Tag, known: set[str]) -> list[str]:
    """Retire la page de titre de la source (auteur, titre, date, mentions du site).

    Seuls les blocs identifiés comme tels — et ce qui les précède — sont retirés :
    une préface sans titre placée après eux est conservée.
    """
    first = next((h for h in body.find_all(["h1", "h2", "h3"]) if text_of(h)), None)
    if first is None:
        return []
    ancestors = set(id(a) for a in first.parents)
    blocks = [b for b in first.find_all_previous(["p", "h1", "h2", "h3", "h4", "h5", "h6"])
              if id(b) not in ancestors]
    blocks.reverse()
    cut = -1
    for index, block in enumerate(blocks):
        text = text_of(block)
        classes = {c.lower() for c in _classes(block)}
        if classes & TITLE_CLASSES or (text and (
                normalize_words(text) in known or FRONT_RE.search(text)
                or PUBLISHER_RE.search(text))):
            cut = index
    removed = []
    for block in blocks[:cut + 1]:
        text = text_of(block)
        if text:
            removed.append(text)
        block.decompose()
    return removed


def _classes(tag: Tag) -> list[str]:
    if getattr(tag, "attrs", None) is None:
        return []
    value = tag.get("class") or []
    return [value] if isinstance(value, str) else list(value)


def _style(tag: Tag) -> str:
    return (tag.get("style") or "").lower().replace("\n", " ")


def _note_number(value: str) -> str | None:
    match = re.search(r"_?ftn(?:ref)?(\d+)$", value or "")
    return match.group(1) if match else None


TITLE_LINK_RE = re.compile(r"^(?:ou|or|et|suivi(?:e)?s? de|précédée? de|avec)$", re.I)


def join_title_lines(lines: list[str]) -> str:
    """Joint les lignes d'un titre : « ou » + « LE SECRET » -> « ou LE SECRET »."""
    out = ""
    for line in lines:
        if not out:
            out = line
        elif TITLE_LINK_RE.match(out.split(" – ")[-1]):
            out += " " + line
        else:
            out += " – " + line
    return out


def title_separator(subtitle: str) -> str:
    """« LES CAPUCINS ou LE SECRET… » mais « LES MISÉRABLES – Tome I »."""
    return " " if re.match(r"(?i)ou\b", subtitle or "") else " – "


def extract_metadata(soup: BeautifulSoup, book: Book) -> None:
    def first(selectors: str) -> Tag | None:
        return soup.select_one(selectors)

    for author in soup.select(".Auteur, .auteur, .book-author"):
        value = text_of(author)
        if value and not PUBLISHER_RE.search(value) and len(value) < 80:
            book.author = value
            break
    title = first(".Titrelivre, .titrelivre, .book-title")
    if title:
        for br in title.find_all("br"):
            br.replace_with("\n")
        lines = [re.sub(r"\s+", " ", line.replace("\xa0", " ")).strip()
                 for line in title.get_text().split("\n")]
        lines = [line for line in lines if line]
        if lines:
            book.title = lines[0]
            book.subtitle = join_title_lines(lines[1:])
    if not book.title:
        tag = soup.find("title")
        if tag:
            book.title = re.sub(r"\s+", " ", tag.get_text()).split(" - ")[0].strip()
    date = first(".DateSortie, .datesortie, .book-year")
    if date:
        match = YEAR_RE.search(text_of(date))
        if match:
            book.year = match.group(1)


def collect_notes(soup: BeautifulSoup) -> dict[str, Tag]:
    """Récupère le texte des notes (Word ``div#ftnN`` ou ``.footnote-text``)."""
    notes: dict[str, Tag] = {}
    for div in soup.find_all("div", id=re.compile(r"^ftn\d+$")):
        number = _note_number(div["id"])
        for anchor in div.find_all("a", href=re.compile(r"_ftnref\d+")):
            anchor.decompose()
        notes[number] = div.extract()
    for para in soup.select("p.footnote-text"):
        num = para.find(class_="footnote-num")
        match = re.search(r"\d+", num.get_text() if num else para.get_text())
        if not match:
            continue
        if num:
            num.decompose()
        notes[match.group(0)] = para.extract()
    for section in soup.select(".footnotes-section"):
        section.decompose()
    # Le séparateur des notes Word (<div><br clear=all><hr></div>) devient vide : il sera retiré.
    return notes


def note_inline_html(note: Tag) -> str:
    """Contenu d'une note en une seule ligne de HTML inline."""
    parts = []
    blocks = note.find_all("p") or [note]
    for block in blocks:
        fragment = BeautifulSoup(str(block), "lxml")
        container = fragment.body.find() if fragment.body else fragment
        inner = sanitize_inline(container)
        inner = re.sub(r"^\s*\[\d+\]\s*", "", inner).strip()
        if inner:
            parts.append(inner)
    return " ".join(parts)


def sanitize_inline(node: Tag) -> str:
    """HTML inline sûr (italique, gras, exposants) à partir d'un fragment."""
    out: list[str] = []
    for child in node.children:
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString):
            out.append(html.escape(str(child), quote=False))
        elif isinstance(child, Tag):
            inner = sanitize_inline(child)
            name = child.name
            if name in ("i", "em", "b", "strong", "sup", "sub"):
                out.append(f"<{name}>{inner}</{name}>" if inner.strip() else inner)
            elif name == "br":
                out.append(" ")
            else:
                out.append(inner)
    return re.sub(r"\s+", " ", "".join(out).replace("\xa0", " "))


def classify_paragraph(p: Tag) -> str | None:
    classes = [c.lower() for c in _classes(p)]
    style = _style(p)
    align = (p.get("align") or "").lower()
    found = re.search(r"text-align\s*:\s*(\w+)", style)
    align = found.group(1) if found else align
    if "stanza-break" in classes:
        return "blank"
    if align == "center" or any(c in ("centr", "etoile", "align-center") for c in classes):
        return "center"
    if align == "right" or "align-right" in classes:
        return "right"
    if any(c.startswith("taille-1retrait") or c.startswith("taille-1suspendu")
           or c.startswith("msobodytextindent") for c in classes):
        return "quote"
    left = re.search(r"margin-left\s*:\s*(-?[\d.]+)\s*(cm|pt|mm|in)", style)
    if left:
        value = float(left.group(1)) * {"cm": 1, "mm": .1, "pt": .03528, "in": 2.54}[left.group(2)]
        if value >= 0.9:
            return "quote"
    if any(c.startswith("taille-1") for c in classes):
        return "small"
    return None


VERSE_MAX = 78


def _verse_like(text: str) -> bool:
    if not (2 <= len(text) <= VERSE_MAX):
        return False
    if text[0] in "–—-":
        return False
    letter = next((c for c in text if c.isalpha()), "")
    return bool(letter) and letter.isupper()


def mark_verse(blocks: list[Tag], book: Book) -> None:
    """Repère les vers (une ligne par paragraphe) pour les composer sans justification."""
    lines = [b for b in blocks if b.name == "p" and not b.get("class")]
    if not lines:
        return
    verse_ratio = sum(_verse_like(text_of(b)) for b in lines) / len(lines)
    minimum_run = 2 if verse_ratio > 0.5 else 4
    run: list[Tag] = []

    def flush() -> None:
        if len(run) >= minimum_run:
            endings = sum(bool(re.search(r"[.!?…»]$", text_of(b))) for b in run)
            if endings / len(run) < 0.7 or verse_ratio > 0.5:
                for b in run:
                    b["class"] = "v"
                book.verse_lines += len(run)
        run.clear()

    for block in blocks:
        cls = block.get("class")
        if block.name == "p" and not cls and _verse_like(text_of(block)):
            run.append(block)
        elif block.name == "p" and cls in ("blank", "center", "right"):
            continue  # strophes, noms de personnages, hémistiches : la série continue
        else:
            flush()
    flush()


def french_spacing(text: str) -> str:
    text = re.sub(r"[   ]+([;:!?»])", " \\1", text)
    text = re.sub(r"«[   ]+", "« ", text)
    return text


def load_replacements(folder: Path) -> dict[str, str]:
    """``remplacements.json`` : images de la source à remplacer par du texte."""
    path = folder / "remplacements.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {key: value for key, value in data.items() if not key.startswith("_")}


def image_name(src: str) -> str:
    return urllib.parse.unquote(src.split("?")[0].split("#")[0].rstrip("/").split("/")[-1])


def process_images(soup: BeautifulSoup, body: Tag, source: Path, book: Book | None) -> None:
    """Remplace, conserve ou retire chaque image de la source.

    - image listée dans ``remplacements.json`` -> remplacée par son texte (mots grecs…) ;
    - image avant le premier titre (portrait, couverture) -> retirée ;
    - image du texte présente dans ``<dossier source>/images/`` -> conservée ;
    - sinon retirée, avec une alerte dans le rapport.
    """
    replacements = load_replacements(source.parent)
    images_dir = source.parent / "images"
    for img in body.find_all("img"):
        name = image_name(img.get("src") or "")
        if name in replacements:
            img.replace_with(replacements[name])
            if book is not None:
                book.report.append(f"Image « {name} » remplacée par le texte « {replacements[name]} ».")
            continue
        front = img.find_previous(["h1", "h2", "h3"]) is None
        local = next((c for c in (images_dir / name, images_dir / name.replace(" ", "_"))
                      if c.is_file()), None)
        if book is None or front or local is None:
            if book is not None and not front:
                parent = img.find_parent(["p", "div"]) or img.parent
                context = text_of(parent)[-80:] if parent else ""
                book.warnings.append(
                    f"Image de contenu introuvable « {name} » (après : « {context} ») : "
                    f"placez-la dans {images_dir} ou ajoutez un texte dans remplacements.json.")
            elif book is not None:
                book.report.append(f"Image de couverture/portrait retirée : {name}")
            img.decompose()
            continue
        try:
            width = int(re.sub(r"\D", "", str(img.get("width") or "")) or 0)
        except ValueError:
            width = 0
        try:
            from PIL import Image
            with Image.open(local) as picture:
                natural = picture.width
        except Exception:  # pragma: no cover - Pillow vient avec WeasyPrint
            natural = width
        width = width or natural
        parent = img.find_parent("p")
        alone = parent is not None and not text_of(parent)
        book.image_files[local.name] = local
        new = soup.new_tag("img", attrs={"src": "images/" + urllib.parse.quote(local.name), "alt": "",
                                         "class": "fig" if alone else "inl",
                                         "style": f"width:{width}px"})
        img.replace_with(new)
        book.images_kept += 1
        # résolution effective une fois imprimée (largeur de texte ~ 4,7 po au plus)
        shown_inches = min(width / 96, 4.7)
        dpi = natural / shown_inches if shown_inches else 0
        if dpi < 200:
            book.low_res.append(f"{name} (~{dpi:.0f} dpi)")


def clean_book(source: Path, notes_mode: str = "auto") -> Book:
    book = Book(source=source)
    raw = load_source(source)
    soup = BeautifulSoup(raw, "lxml")
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    extract_metadata(soup, book)
    if not book.title:
        book.title = source.stem
    front_text = " ".join(text_of(t) for t in soup.select(".DateSortie, .Titrelivre, .book-year"))
    annotated = bool(ANNOTATED_RE.search(front_text))

    body = soup.body or soup
    process_images(soup, body, source, book)
    for name in DROP_TAGS:
        for tag in body.find_all(name):
            tag.decompose()

    # Notes : on récupère leur texte avant de retirer les annexes de fin.
    notes = collect_notes(soup)

    # Fin de document : « À propos de cette édition électronique » et tout ce qui suit.
    for tag in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p"]):
        if normalize_words(text_of(tag)) == ABOUT_HEADING:
            _remove_after(tag)
            book.report.append("Page « À propos de cette édition électronique » retirée.")
            break

    # Table des matières de la source (sera régénérée avec les vrais numéros de page).
    toc_count = 0
    for tag in body.find_all(True):
        if getattr(tag, "decomposed", False):
            continue
        classes = [c.lower() for c in _classes(tag)]
        if any(c.startswith("msotoc") or c in ("titretablematires", "toc", "sommaire",
                                                "table-des-matieres") for c in classes):
            tag.decompose()
            toc_count += 1
    for tag in body.find_all(["h1", "h2", "h3", "h4", "p"]):
        if normalize_words(text_of(tag)) in TOC_HEADINGS:
            tag.decompose()
            toc_count += 1
    if toc_count:
        book.report.append(f"Ancienne table des matières retirée ({toc_count} lignes).")

    # Page de titre de la source : tout ce qui précède le premier titre de l'œuvre.
    for tag in body.select(".title-page"):
        tag.decompose()
    known = {normalize_words(x) for x in (book.author, book.title, book.subtitle) if x}
    known.add(normalize_words(f"{book.title} {book.subtitle}"))
    removed = strip_front_matter(body, known)
    if removed:
        book.report.append("Page de titre d'origine retirée : "
                           + " / ".join(t[:70] for t in removed))
        if not book.year:
            match = YEAR_RE.search(" ".join(removed))
            if match:
                book.year = match.group(1)

    # Appels de notes.
    if notes_mode == "auto":
        notes_mode = "remove" if annotated else "keep"
        if annotated:
            book.warnings.append("Notes d'un éditeur moderne détectées (« texte annoté ») : "
                                 "elles sont protégées par le droit d'auteur et ont été retirées.")
    refs: list[tuple[Tag, str]] = []
    for anchor in body.find_all("a", href=re.compile(r"_ftn\d+$")):
        refs.append((anchor, _note_number(anchor["href"])))
    for sup in body.select("sup.footnote-ref"):
        match = re.search(r"\d+", sup.get_text())
        if match:
            refs.append((sup, match.group(0)))
    for ref, number in refs:
        note = notes.get(number)
        content = note_inline_html(note) if note is not None else ""
        keep = notes_mode == "keep" and content and not EDITOR_NOTE_RE.search(content)
        if keep:
            span = BeautifulSoup(f'<span class="fn">{content}</span>', "lxml").span
            ref.replace_with(span.extract())
            book.notes_kept += 1
        else:
            ref.decompose()
            book.notes_removed += 1
    # Appels orphelins du type [12] restés dans le texte.
    for text in body.find_all(string=re.compile(r"\[\d{1,3}\]")):
        text.replace_with(re.sub(r"\s?\[\d{1,3}\]", "", str(text)))

    # Mise à plat de la structure : on garde paragraphes, titres et mise en forme simple.
    for center in body.find_all("center"):
        for p in center.find_all("p"):
            p["align"] = "center"
        center.unwrap()
    for tag in body.find_all(True):
        if tag.name == "p":
            tag["data-k"] = classify_paragraph(tag) or ""
    for tag in list(body.find_all(True)):
        name = tag.name
        if ":" in name:  # balises Word du type <o:p>
            tag.unwrap()
        elif name in STRUCT_KEEP or name in INLINE_KEEP:
            continue
        elif name == "span" and "fn" in _classes(tag):
            continue
        else:
            tag.unwrap()
    for tag in body.find_all(True):
        if tag.name == "img":
            tag.attrs = {k: v for k, v in tag.attrs.items() if k in ("src", "alt", "class", "style")}
            continue
        keep_class = tag.get("data-k") if tag.name == "p" else (
            "fn" if tag.name == "span" and "fn" in _classes(tag) else None)
        tag.attrs = {}
        if keep_class:
            tag["class"] = keep_class
    for br in body.find_all("br"):  # sauts de ligne en tête ou fin de bloc
        parent = br.parent
        if parent and parent.name in BLOCK_TAGS:
            if not any(isinstance(s, Tag) or str(s).strip() for s in br.previous_siblings) \
                    or not any(isinstance(s, Tag) or str(s).strip() for s in br.next_siblings):
                br.decompose()

    # Texte : espaces, liens visibles, espaces insécables à la française.
    urls = 0
    for node in list(body.find_all(string=True)):
        value = str(node)
        value = value.replace("\u00ad", "").replace("\u200b", "").replace("\ufeff", "")
        value = re.sub(r"[ \t\r\n]+", " ", value)
        value, count = URL_RE.subn("", value)
        urls += count
        value = french_spacing(value)
        if value != str(node):
            node.replace_with(value)
    if urls:
        book.report.append(f"{urls} adresse(s) web retirée(s) du texte.")

    # Blocs de premier niveau : paragraphes hors bloc regroupés, blocs vides convertis.
    blocks: list[Tag] = []
    loose: list = []

    def flush_loose() -> None:
        if loose and "".join(str(x) for x in loose).strip():
            p = soup.new_tag("p")
            for item in loose:
                p.append(item)
            blocks.append(p)
        loose.clear()

    for child in list(body.children):
        if isinstance(child, Tag) and child.name in STRUCT_KEEP:
            flush_loose()
            blocks.append(child.extract())
        else:
            loose.append(child.extract())
    flush_loose()

    cleaned: list[Tag] = []
    for block in blocks:
        for inline in block.find_all(["i", "em", "b", "strong", "u", "s", "small"]):
            if not inline.get_text().strip():
                inline.unwrap()
        empty = not block.get_text().replace("\xa0", " ").strip() and not block.find("img")
        if block.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if empty:
                continue
        elif block.name == "p" and empty:
            block.attrs = {"class": "blank"}
            block.clear()
        elif empty:
            continue
        if block.name == "p" and block.get("class") == "blank" and not empty:
            del block["class"]
        # espaces de début et de fin de bloc
        first = next(block.strings, None)
        if first is not None and first.lstrip(" \xa0") != first:
            first.replace_with(first.lstrip(" \xa0"))
        last = None
        for last in block.strings:
            pass
        if last is not None and last.rstrip(" \xa0") != last:
            last.replace_with(last.rstrip(" \xa0"))
        cleaned.append(block)

    # Lignes blanches : une seule à la suite, aucune autour des titres ni aux extrémités.
    result: list[Tag] = []
    for block in cleaned:
        is_blank = block.get("class") == "blank"
        is_heading = block.name in ("h1", "h2", "h3", "h4", "h5", "h6")
        if is_blank and (not result or result[-1].get("class") == "blank"
                         or result[-1].name in ("h1", "h2", "h3", "h4", "h5", "h6")):
            continue
        if is_heading:
            while result and result[-1].get("class") == "blank":
                result.pop()
        result.append(block)
    while result and result[-1].get("class") == "blank":
        result.pop()

    # Mentions éditoriales du site source restées dans le corps du texte.
    filtered = []
    for block in result:
        if PUBLISHER_RE.search(block.get_text()):
            book.report.append("Mention éditoriale retirée : « "
                               + text_of(block)[:80] + " »")
            continue
        filtered.append(block)
    result = filtered

    mark_verse(result, book)

    # Titres : identifiants pour la table des matières et texte du titre courant.
    counter = 0
    for block in result:
        if block.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            counter += 1
            ident = f"t{counter}"
            parts = []
            clone = BeautifulSoup(str(block), "lxml").find(block.name)
            for fn in clone.select("span.fn"):
                fn.decompose()
            for br in clone.find_all("br"):
                br.replace_with("\n")
            for line in clone.get_text().split("\n"):
                line = re.sub(r"\s+", " ", line.replace("\xa0", " ")).strip()
                if line:
                    parts.append(line)
            label = " – ".join(parts)
            block["id"] = ident
            block["data-rh"] = label if len(label) <= 60 else label[:57].rstrip(" ,;–") + "…"
            book.headings.append((int(block.name[1]), ident, label))

    book.body = "\n".join(str(b) for b in result)

    # Contrôle d'intégrité : mêmes mots qu'à l'entrée, notes mises à part.
    check = BeautifulSoup(book.body, "lxml")
    for fn in check.select("span.fn"):
        fn.decompose()
    book.words_output = len(words(check.get_text(" ")))
    book.words_source = book.words_output  # recalculé dans verify_words()
    verify_words(book, raw, notes)
    scan_residues(book)
    return book


def _block_text(root: Tag) -> str:
    """Texte avec un espace entre les blocs, mais sans en ajouter entre balises inline."""
    for tag in root.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "br", "li", "td",
                              "th", "div", "blockquote", "tr"]):
        if tag.name == "br":
            tag.insert_after(" ")
        else:
            tag.append(" ")
    return root.get_text("")


def verify_words(book: Book, raw: str, notes: dict[str, Tag]) -> None:
    """Compare les mots du texte final avec ceux de la source (hors annexes)."""
    soup = BeautifulSoup(raw, "lxml")
    body = soup.body or soup
    process_images(soup, body, book.source, None)
    for name in DROP_TAGS:
        for tag in body.find_all(name):
            tag.decompose()
    for div in soup.find_all("div", id=re.compile(r"^ftn\d+$")):
        div.decompose()
    for tag in soup.select(".footnotes-section, .title-page"):
        tag.decompose()
    for tag in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p"]):
        if normalize_words(text_of(tag)) == ABOUT_HEADING:
            _remove_after(tag)
            break
    for tag in body.find_all(True):
        classes = [c.lower() for c in _classes(tag)]
        if any(c.startswith("msotoc") or c == "titretablematires" for c in classes):
            tag.decompose()
    for tag in body.find_all(["h1", "h2", "h3", "h4", "p"]):
        if normalize_words(text_of(tag)) in TOC_HEADINGS:
            tag.decompose()
    known = {normalize_words(x) for x in (book.author, book.title, book.subtitle) if x}
    known.add(normalize_words(f"{book.title} {book.subtitle}"))
    strip_front_matter(body, known)
    for anchor in body.find_all("a", href=re.compile(r"_ftn\d+$")):
        anchor.decompose()
    for sup in body.select("sup.footnote-ref"):
        sup.decompose()
    for tag in body.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6"]):
        if PUBLISHER_RE.search(tag.get_text()):
            tag.decompose()
    text = _block_text(body)
    text = URL_RE.sub(" ", re.sub(r"\[\d{1,3}\]", " ", text.replace("\u00ad", "")))
    expected = words(text)
    check = BeautifulSoup(book.body, "lxml")
    for fn in check.select("span.fn"):
        fn.decompose()
    got = words(_block_text(check))
    book.words_source = len(expected)
    book.words_output = len(got)
    book.words_match = expected == got
    if not book.words_match:
        start = next((i for i, (a, b) in enumerate(zip(expected, got)) if a != b),
                     min(len(expected), len(got)))
        end_a, end_b = len(expected), len(got)
        while end_a > start and end_b > start and expected[end_a - 1] == got[end_b - 1]:
            end_a -= 1
            end_b -= 1
        book.warnings.append(
            f"Écart de texte : source « {' '.join(expected[max(0, start - 4):min(end_a, start + 12) + 4])} »"
            f" → sortie « {' '.join(got[max(0, start - 4):min(end_b, start + 12) + 4])} »")


def scan_residues(book: Book) -> None:
    text = BeautifulSoup(book.body, "lxml").get_text(" ")
    checks = {
        "adresse web": r"(?i)https?:|www\.|\.com\b",
        "mention du site source": r"(?i)ebooks?\s*libres|ebooksgratuits",
        "appel de note entre crochets": r"\[\d+\]",
        "ancienne table des matières": r"(?i)table des mati[èe]res",
    }
    for label, pattern in checks.items():
        found = re.findall(pattern, text)
        if found:
            book.warnings.append(f"Reste possible ({label}) : {len(found)} occurrence(s).")


# ---------------------------------------------------------------------------
# Mise en page (HTML imprimable -> PDF via WeasyPrint)
# ---------------------------------------------------------------------------

@dataclass
class Layout:
    width: float = 6.0
    height: float = 9.0
    font_size: float = 11.0
    line_height: float = 1.38
    inside: float = 0.875
    toc: str = "fin"            # fin | debut | aucune
    chapter_recto: bool = True  # les grandes parties commencent en page impaire
    publisher: str = ""
    isbn: str = ""


def font_faces() -> str:
    faces = [("Regular", "normal", 400), ("Italic", "italic", 400),
             ("Bold", "normal", 700), ("BoldItalic", "italic", 700)]
    rules = []
    for name, style, weight in faces:
        path = FONTS_DIR / f"EBGaramond-{name}.ttf"
        if path.exists():
            rules.append(f"@font-face{{font-family:'EB Garamond';font-style:{style};"
                         f"font-weight:{weight};src:url('fonts/{path.name}');}}")
    return "\n".join(rules)


def print_css(layout: Layout) -> str:
    w, h, inside = layout.width, layout.height, layout.inside
    out = OUTSIDE_MARGIN
    first_break = "right" if layout.chapter_recto else "page"
    return f"""
{font_faces()}
@page {{
  size: {w}in {h}in;
  margin: {TOP_MARGIN}in {out}in {BOTTOM_MARGIN}in {inside}in;
  @top-center {{ content: string(rh-right, first-except); font: italic 8.5pt 'EB Garamond', serif;
                 color: #222; vertical-align: middle; }}
  @bottom-center {{ content: counter(page); font: 9.5pt 'EB Garamond', serif; vertical-align: middle; }}
  @footnote {{ border-top: 0.4pt solid #444; padding-top: 4pt; margin-top: 10pt; }}
}}
@page :left {{
  margin-left: {out}in; margin-right: {inside}in;
  @top-center {{ content: string(rh-left, first-except); font: 8.5pt 'EB Garamond', serif;
                 letter-spacing: .12em; text-transform: uppercase; }}
}}
@page :right {{ margin-left: {inside}in; margin-right: {out}in; }}
@page :blank {{ @top-center {{ content: none; }} @bottom-center {{ content: none; }} }}
@page front {{ @top-center {{ content: none; }} @bottom-center {{ content: none; }} }}
@page tocpage {{ @top-center {{ content: none; }} }}

html {{ font-family: 'EB Garamond', Garamond, Georgia, serif; font-size: {layout.font_size}pt;
        line-height: {layout.line_height}; color: #000; }}
body {{ margin: 0; font-kerning: normal; font-variant-ligatures: common-ligatures; }}

.front {{ page: front; }}
.title-page {{ break-after: page; text-align: center; }}
.title-page .author {{ margin-top: 12%; font-size: 1.25em; letter-spacing: .2em; text-transform: uppercase; }}
.title-page .title {{ margin-top: 22%; font-size: 2.1em; line-height: 1.15; letter-spacing: .06em;
                      text-transform: uppercase; font-weight: normal; }}
.title-page .subtitle {{ margin-top: 1em; font-size: 1.2em; font-style: italic; }}
.title-page .ornament {{ margin-top: 1.4em; font-size: 1.1em; }}
.title-page .year {{ margin-top: {(h - 4.5) * 0.5 + 0.8:.2f}in; font-size: 1em; letter-spacing: .1em; }}
.title-page .publisher {{ margin-top: .6em; font-size: .9em; letter-spacing: .15em; text-transform: uppercase; }}
.legal {{ break-after: right; height: {h - TOP_MARGIN - BOTTOM_MARGIN - 0.1}in; display: flex;
          flex-direction: column; justify-content: flex-end; font-size: .82em; line-height: 1.5; }}
.legal p {{ margin: 0 0 .5em; text-indent: 0; text-align: left; hyphens: manual; }}

p {{ margin: 0; text-indent: 1.25em; text-align: justify; hyphens: auto; orphans: 2; widows: 2; }}
h1 + p, h2 + p, h3 + p, h4 + p, h5 + p, h6 + p, p.blank + p, p.center + p:not(.v),
p.quote + p, p.right + p {{ text-indent: 0; }}
p.blank {{ height: .75em; }}
p.center {{ text-align: center; text-indent: 0; hyphens: manual; }}
p.right {{ text-align: right; text-indent: 0; hyphens: manual; }}
p.quote {{ margin-left: 1.5em; margin-right: 1em; text-indent: 0; font-size: .95em; }}
p.small {{ font-size: .95em; }}
p.v {{ text-align: left; text-indent: -1.5em !important; padding-left: 2.5em; hyphens: manual; }}
blockquote {{ margin: .5em 1.5em; font-size: .95em; }}
img {{ max-width: 100%; height: auto; }}
img.fig {{ display: block; margin: .6em auto; break-inside: avoid; }}
img.inl {{ vertical-align: middle; max-height: 2.2em; width: auto !important; }}
p:has(> img.fig) {{ text-indent: 0; text-align: center; }}
table {{ margin: .6em auto; border-collapse: collapse; font-size: .9em; }}
td, th {{ padding: 2pt 5pt; vertical-align: top; }}
td p, th p {{ text-indent: 0; text-align: left; }}

h1, h2, h3, h4, h5, h6 {{ font-weight: normal; text-align: center; hyphens: manual;
  break-after: avoid; break-inside: avoid; line-height: 1.25; }}
h1 {{ break-before: {first_break}; margin: 22% 0 2.2em; font-size: 1.45em; letter-spacing: .08em;
      text-transform: uppercase; string-set: rh-right attr(data-rh), rh-left attr(data-book); }}
h2 {{ break-before: page; margin: 18% 0 1.8em; font-size: 1.2em; letter-spacing: .05em;
      string-set: rh-right attr(data-rh), rh-left attr(data-book); }}
h1 + h2 {{ break-before: avoid; margin-top: 0; }}
h3 {{ margin: 2.2em 0 1.1em; font-size: 1.08em; letter-spacing: .03em; }}
h4 {{ margin: 1.8em 0 .9em; font-size: 1em; font-style: italic; }}
h5, h6 {{ margin: 1.4em 0 .7em; font-size: .95em; letter-spacing: .05em; }}
h1 + h3, h2 + h3, h3 + h4, h3 + h5, h4 + h5 {{ margin-top: 0; }}

.fn {{ float: footnote; font-size: 8.5pt; line-height: 1.3; text-indent: 0; text-align: justify;
       font-style: normal; font-weight: normal; letter-spacing: 0; text-transform: none; }}
::footnote-call {{ content: counter(footnote); vertical-align: super; font-size: 65%; line-height: 0; }}
::footnote-marker {{ content: counter(footnote) ".\\00a0"; }}
sup {{ font-size: .7em; line-height: 0; }}

.toc {{ page: tocpage; break-before: right; }}
.toc h1 {{ string-set: none; }}
.toc ul {{ list-style: none; margin: 0; padding: 0; }}
.toc li {{ margin: 0 0 .25em; text-indent: -1.2em; padding-left: 1.2em; hyphens: manual; }}
.toc li.l2 {{ margin-left: 1.2em; }}
.toc li.l3 {{ margin-left: 2.4em; font-size: .95em; }}
.toc li.top {{ margin-top: .7em; }}
.toc a {{ color: inherit; text-decoration: none; }}
.toc a::after {{ content: leader('.') target-counter(attr(href), page); }}
""".strip()


def toc_entries(book: Book) -> list[tuple[int, str, str]]:
    levels = sorted({level for level, _, _ in book.headings})
    if not levels:
        return []
    depth: list[int] = []
    for level in levels:
        count = sum(1 for lv, _, _ in book.headings if lv in depth or lv == level)
        if depth and count > 200:
            break
        depth.append(level)
        if len(depth) == 3:
            break
    return [entry for entry in book.headings if entry[0] in depth]


def build_print_html(book: Book, layout: Layout) -> str:
    esc = lambda value: html.escape(value or "", quote=True)  # noqa: E731
    title, author = book.title, book.author
    subtitle_sep = title_separator(book.subtitle)
    legal = [
        f"<p><i>{esc(title)}</i>{subtitle_sep + esc(book.subtitle) if book.subtitle else ''}</p>",
        f"<p>{esc(author)}</p>" if author else "",
        (f"<p>Texte original publié en {esc(book.year)}, appartenant au domaine public.</p>"
         if book.year else "<p>Texte appartenant au domaine public.</p>"),
        "<p>Composé en EB Garamond.</p>",
        f"<p>{esc(layout.publisher)}</p>" if layout.publisher else "",
        f"<p>ISBN : {esc(layout.isbn)}</p>" if layout.isbn else "",
    ]
    year = f'<div class="year">{esc(book.year)}</div>' if book.year else ""
    publisher = f'<div class="publisher">{esc(layout.publisher)}</div>' if layout.publisher else ""
    subtitle = f'<div class="subtitle">{esc(book.subtitle)}</div>' if book.subtitle else ""
    front = f"""<div class="front">
<div class="title-page"><div class="author">{esc(author)}</div><div class="title">{esc(title)}</div>
{subtitle}<div class="ornament">❦</div>{year}{publisher}</div>
<div class="legal">{''.join(legal)}</div>
</div>"""
    toc = ""
    entries = toc_entries(book)
    if layout.toc != "aucune" and entries:
        top = min(level for level, _, _ in entries)
        levels = sorted({level for level, _, _ in entries})
        items = []
        for level, ident, label in entries:
            rank = levels.index(level) + 1
            cls = f"l{rank}" + (" top" if level == top and len(levels) > 1 else "")
            items.append(f'<li class="{cls}"><a href="#{ident}">{esc(label)}</a></li>')
        toc = (f'<div class="toc"><h1>Table des matières</h1><ul>{"".join(items)}</ul></div>')
    body = book.body
    rh_book = title if len(title) <= 50 else title[:47] + "…"
    content = f'<div class="book" data-book="{esc(rh_book)}">\n{body}\n</div>'
    # data-book doit aussi figurer sur chaque titre pour le titre courant de gauche.
    content = re.sub(r"<(h[12]) ", lambda m: f'<{m.group(1)} data-book="{esc(rh_book)}" ', content)
    parts = [front]
    if layout.toc == "debut":
        parts.append(toc)
    parts.append(content)
    if layout.toc == "fin":
        parts.append(toc)
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>{esc(title)} — {esc(author)}</title>
<meta name="author" content="{esc(author)}">
<style>
{print_css(layout)}
</style>
</head>
<body>
{''.join(parts)}
</body>
</html>
"""


def copy_assets(book: Book, folder: Path) -> None:
    """Copie polices et images à côté du HTML : le dossier reste autonome et déplaçable."""
    fonts = folder / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    for font in list(FONTS_DIR.glob("EBGaramond-*.ttf")) + [FONTS_DIR / "OFL.txt"]:
        if font.is_file():
            shutil.copy2(font, fonts / font.name)
    if book.image_files:
        images = folder / "images"
        images.mkdir(exist_ok=True)
        for name, path in book.image_files.items():
            shutil.copy2(path, images / name)


def render_pdf(book: Book, layout: Layout, pdf_path: Path, log) -> tuple[int, Layout]:
    try:
        from weasyprint import HTML
    except ImportError:  # pragma: no cover
        raise SystemExit("WeasyPrint n'est pas installé : pip install -r requirements.txt")
    copy_assets(book, pdf_path.parent)
    tried: dict[float, object] = {}
    inside = layout.inside
    document = None
    for _ in range(4):
        layout.inside = inside
        start = time.time()
        document = HTML(string=build_print_html(book, layout), base_url=str(pdf_path.parent) + "/").render()
        pages = len(document.pages)
        log(f"   rendu : {pages} pages avec petit fond {inside:.3f} po ({time.time() - start:.0f} s)")
        tried[inside] = document
        needed = round(kdp_min_gutter(pages) + GUTTER_COMFORT, 3)
        if needed == inside or (needed < inside and needed in tried):
            break
        inside = needed
    document.write_pdf(pdf_path)
    return len(document.pages), layout


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def slugify(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value)
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]+", "-", plain).strip("-").lower() or "livre"


def process(source: Path, output_dir: Path, options: dict) -> tuple[str, bool, str]:
    lines: list[str] = []
    log = lines.append
    try:
        book = clean_book(source, options["notes"])
        slug = slugify(source.stem)
        folder = output_dir / slug
        folder.mkdir(parents=True, exist_ok=True)
        # Beaucoup de titres de niveau 1 = ce sont des chapitres : pas de page blanche avant.
        many_parts = sum(1 for level, _, _ in book.headings if level == 1) > 25
        layout = Layout(width=options["size"][0], height=options["size"][1],
                        font_size=options["font_size"], toc=options["toc"],
                        chapter_recto=options["recto"] and not many_parts,
                        publisher=options["publisher"], isbn=options["isbn"])
        copy_assets(book, folder)
        (folder / f"{slug}.html").write_text(build_print_html(book, layout), encoding="utf-8")
        pages = None
        if options["pdf"]:
            fmt = f"{layout.width:g}x{layout.height:g}"
            pdf_path = folder / f"{slug}_interieur_{fmt}.pdf"
            pages, layout = render_pdf(book, layout, pdf_path, log)
            (folder / f"{slug}.html").write_text(build_print_html(book, layout), encoding="utf-8")
            if pages > KDP_MAX_PAGES:
                book.warnings.append(
                    f"{pages} pages : au-delà du maximum KDP ({KDP_MAX_PAGES}). "
                    "Choisissez un format plus grand (--format 7x10), une police plus petite "
                    "(--taille-police 10) ou découpez le livre en volumes.")
            elif pages < KDP_MIN_PAGES:
                book.warnings.append(f"{pages} pages : en dessous du minimum KDP ({KDP_MIN_PAGES}).")
        report = write_report(book, layout, pages, folder / "rapport.txt", lines)
        ok = book.words_match and not any(w.startswith("Écart") for w in book.warnings)
        return source.name, ok, report
    except Exception as error:  # un livre défectueux ne bloque pas les autres
        import traceback
        return source.name, False, f"ERREUR : {error}\n{traceback.format_exc()}"


def write_report(book: Book, layout: Layout, pages: int | None, path: Path,
                 render_log: list[str]) -> str:
    out = [f"{book.title}{title_separator(book.subtitle) + book.subtitle if book.subtitle else ''}",
           f"Auteur : {book.author or '?'}   Année : {book.year or '?'}",
           f"Source : {book.source.name}", ""]
    out.append(f"Mots du texte : {book.words_output} "
               + ("(identiques à la source ✔)" if book.words_match
                  else f"(source : {book.words_source} ✘ À VÉRIFIER)"))
    out.append(f"Notes conservées en bas de page : {book.notes_kept}   "
               f"notes retirées : {book.notes_removed}")
    if book.images_kept:
        out.append(f"Images conservées : {book.images_kept}")
    if book.low_res:
        book.warnings.append("Images en basse résolution (KDP recommande 300 dpi, elles "
                             "seront imprimées floues) : " + ", ".join(book.low_res))
    if book.verse_lines:
        out.append(f"Vers détectés (composés sans justification) : {book.verse_lines}")
    if pages:
        out.append(f"PDF : {pages} pages, format {layout.width:g} x {layout.height:g} po, "
                   f"petit fond {layout.inside:.3f} po (minimum KDP {kdp_min_gutter(pages)} po), "
                   f"grand fond {OUTSIDE_MARGIN} po, sans fond perdu, polices incorporées.")
    out += [""] + [f"- {line}" for line in book.report]
    if book.warnings:
        out += ["", "À VÉRIFIER :"] + [f"! {w}" for w in book.warnings]
    out += [""] + render_log
    text = "\n".join(out) + "\n"
    path.write_text(text, encoding="utf-8")
    return text


def parse_size(value: str) -> tuple[float, float]:
    key = value.lower().replace(",", ".").replace(" ", "").replace("×", "x")
    if key in TRIM_SIZES:
        return TRIM_SIZES[key]
    match = re.fullmatch(r"(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)", key)
    if not match:
        raise argparse.ArgumentTypeError(
            f"format invalide : {value} (exemples : {', '.join(TRIM_SIZES)})")
    return float(match.group(1)), float(match.group(2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Nettoie des livres HTML du domaine public et produit un PDF "
                    "intérieur prêt pour l'impression brochée Amazon KDP.")
    parser.add_argument("fichiers", nargs="*", type=Path,
                        help="Livres à traiter (par défaut : tout le dossier source).")
    parser.add_argument("--dossier-source", "--input-dir", dest="input_dir", type=Path,
                        default=ROOT / "victor-hugo")
    parser.add_argument("--dossier-sortie", "--output-dir", dest="output_dir", type=Path,
                        default=ROOT / "sortie")
    parser.add_argument("--format", type=parse_size, default=TRIM_SIZES["6x9"],
                        help="Format KDP en pouces (défaut 6x9). Ex. : 5x8, 5.5x8.5, 6x9.")
    parser.add_argument("--taille-police", type=float, default=11.0,
                        help="Corps du texte en points (défaut 11).")
    parser.add_argument("--notes", choices=["auto", "garder", "retirer"], default="auto",
                        help="auto : garde les notes d'auteur, retire celles d'un éditeur moderne.")
    parser.add_argument("--sommaire", choices=["fin", "debut", "aucune"], default="fin",
                        help="Position de la table des matières (défaut : fin, usage français).")
    parser.add_argument("--parties-page-impaire", dest="recto", action=argparse.BooleanOptionalAction,
                        default=True, help="Les titres de niveau 1 commencent en page de droite.")
    parser.add_argument("--editeur", default="", help="Nom de votre maison d'édition (facultatif).")
    parser.add_argument("--isbn", default="", help="ISBN à imprimer au verso du titre (facultatif).")
    parser.add_argument("--sans-pdf", dest="pdf", action="store_false",
                        help="Produit seulement le HTML nettoyé (rapide).")
    parser.add_argument("--jobs", type=int, default=0,
                        help="Nombre de livres traités en parallèle (défaut : nombre de cœurs).")
    args = parser.parse_args(argv)

    if args.fichiers:
        sources = [p.resolve() for p in args.fichiers]
        missing = [str(p) for p in sources if not p.is_file()]
        if missing:
            parser.error("fichier introuvable : " + ", ".join(missing))
    else:
        input_dir = args.input_dir.resolve()
        if not input_dir.is_dir():
            parser.error(f"dossier source introuvable : {input_dir}")
        sources = sorted((p for p in input_dir.iterdir()
                          if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES),
                         key=lambda p: p.name.casefold())
    if not sources:
        print("Aucun livre trouvé.")
        return 1
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    options = {
        "notes": {"auto": "auto", "garder": "keep", "retirer": "remove"}[args.notes],
        "size": args.format, "font_size": args.taille_police, "toc": args.sommaire,
        "recto": args.recto, "publisher": args.editeur, "isbn": args.isbn, "pdf": args.pdf,
    }
    import os
    jobs = args.jobs or min(len(sources), os.cpu_count() or 1)
    print(f"{len(sources)} livre(s) → {output_dir}  (format {args.format[0]:g} x {args.format[1]:g} po"
          f"{', sans PDF' if not args.pdf else ''})\n")
    failures = 0
    if jobs <= 1:
        results = (process(s, output_dir, options) for s in sources)
        iterator = results
    else:
        pool = ProcessPoolExecutor(max_workers=jobs)
        futures = [pool.submit(process, s, output_dir, options) for s in sources]
        iterator = (f.result() for f in as_completed(futures))
    for name, ok, report in iterator:
        failures += not ok
        print(("OK      " if ok else "À VOIR  ") + name)
        print("        " + report.strip().replace("\n", "\n        ") + "\n")
    print(f"Terminé : {len(sources) - failures}/{len(sources)} livre(s) sans alerte bloquante.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
