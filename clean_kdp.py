#!/usr/bin/env python3
"""Clean every HTML book in ``victor-hugo/`` for a KDP print interior.

Original files are never changed. Cleaned books are written to
``victor-hugo/cleaned/``; images embedded in Saved-by-Blink (MHTML) archives
are extracted beside them under ``cleaned/assets/``.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path


KDP_CSS = """
@page {
  size: 6in 9in;
  margin-top: 20mm;
  margin-bottom: 20mm;
  margin-inside: 22mm;
  margin-outside: 16mm;
}
@page :left { margin-left: 16mm; margin-right: 22mm; }
@page :right { margin-left: 22mm; margin-right: 16mm; }
html { font-size: 11pt; line-height: 1.45; -webkit-text-size-adjust: 100%; }
body {
  font-family: Georgia, Garamond, "Times New Roman", serif;
  color: #111; background: #fff; margin: 0; padding: 0;
  text-rendering: optimizeLegibility;
}
p { margin: 0; text-indent: 1.5em; text-align: justify; hyphens: auto;
    -webkit-hyphens: auto; orphans: 2; widows: 2; }
h1 + p, h2 + p, h3 + p, h4 + p, h5 + p { text-indent: 0; }
p.align-right { text-align: right; text-indent: 0; margin: .5em 0;
                 font-style: italic; font-size: .9em; }
p.align-center { text-align: center; text-indent: 0; }
p.stanza-break { margin: 0; height: .9em; text-indent: 0; }
.title-page { page-break-after: always; break-after: page; text-align: center;
              padding-top: 25%; min-height: 70vh; }
.title-page .book-author { font-size: 1.6rem; letter-spacing: .15em;
  text-transform: uppercase; margin-bottom: 2rem; text-indent: 0; text-align: center; }
.title-page .book-title { font-size: 2.2rem; font-weight: bold; letter-spacing: .1em;
  line-height: 1.2; margin: 2rem 0; }
.title-page .book-year { font-size: 1.1rem; color: #555; margin-top: 3rem;
  text-indent: 0; text-align: center; }
h1, h2, h3, h4, h5 { text-align: center; font-weight: normal;
                     page-break-after: avoid; break-after: avoid; }
h1 { page-break-before: always; break-before: page; font-size: 1.8rem;
     letter-spacing: .08em; margin: 30% 0 2rem; text-transform: uppercase; }
h2 { page-break-before: always; break-before: page; font-size: 1.4rem;
     letter-spacing: .06em; margin: 20% 0 1.5rem; text-transform: uppercase; }
h3 { font-size: 1.15rem; letter-spacing: .04em; margin: 2rem 0 1rem; }
h4 { font-size: 1.05rem; letter-spacing: .02em; margin: 1.5rem 0 .8rem; }
h5 { font-size: 1rem; letter-spacing: .05em; margin: 1.2rem 0 .6rem; font-weight: bold; }
img { max-width: 100%; height: auto; break-inside: avoid; }
sup.footnote-ref { font-size: .75em; vertical-align: super; line-height: 0; }
.footnotes-section { page-break-before: always; break-before: page; margin-top: 3rem;
  padding-top: 1.5rem; border-top: 1px solid #ccc; }
.footnotes-section h2 { margin-top: 0; page-break-before: avoid; break-before: avoid; }
.footnote-text { font-size: .85rem; line-height: 1.35; margin-bottom: .6rem; text-indent: 0; }
.footnote-num { font-weight: bold; margin-right: .3em; }
""".strip()

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}
DROP_WITH_CONTENT = {"script", "style", "noscript", "nav", "form", "button",
                     "textarea", "select", "iframe", "object", "embed", "svg",
                     "video", "audio", "canvas"}
ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "caption", "center", "cite", "code",
    "dd", "del", "div", "dl", "dt", "em", "figcaption", "figure", "font",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "ins", "li",
    "ol", "p", "pre", "q", "s", "small", "span", "strong", "sub", "sup",
    "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
}
KEEP_CLASSES = {
    "align-right", "align-center", "stanza-break", "footnote-ref",
    "footnotes-section", "footnote-text", "footnote-num", "novel-body",
}
CAPTURE_CLASSES = {
    "book-title": "book_title", "titrelivre": "book_title", "titre-livre": "book_title",
    "book-author": "author", "auteur": "author", "author": "author",
    "book-year": "year", "datesortie": "year", "year": "year",
}


@dataclass
class CleanStats:
    dropped_tags: int = 0
    links_unwrapped: int = 0
    spans_unwrapped: int = 0
    attributes_removed: int = 0
    empty_paragraphs: int = 0
    comments_removed: int = 0
    images_removed: int = 0
    urls_removed: int = 0
    toc_sections_removed: int = 0
    toc_entries_removed: int = 0
    publication_mentions_removed: int = 0


class BookCleaner(HTMLParser):
    """Keep book structure and text while removing web and word-processor markup."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stats = CleanStats()
        self.output: list[str] = []
        self.tag_stack: list[str] = []
        self.skip_stack: list[str] = []
        self.in_body = False
        self.body_seen = False
        self.in_head = False
        self.was_body = False
        self.drop_footer = False
        self.paragraphs: list[dict[str, object]] = []
        self.text_elements: list[dict[str, object]] = []
        self.captures: list[dict[str, str]] = []
        self.metadata: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.drop_footer:
            return
        values = {key.lower(): value or "" for key, value in attrs}
        classes = {item.lower() for item in values.get("class", "").split()}

        for class_name, key in CAPTURE_CLASSES.items():
            if class_name in {item.lower() for item in classes}:
                self.captures.append({"tag": tag, "key": key, "value": ""})
        if tag == "title":
            self.captures.append({"tag": tag, "key": "document_title", "value": ""})

        if tag == "body":
            self.in_body = self.body_seen = True
            return
        if tag == "head":
            self.in_head = True
            return
        if tag == "html":
            return

        if self.skip_stack:
            if tag not in VOID_TAGS:
                self.skip_stack.append(tag)
            return
        if any(name.startswith("msotoc") or name in {
            "toc", "sommaire", "tableofcontents", "table-of-contents",
            "table-des-matieres",
        } for name in classes) or any(name in {
            "toc", "sommaire", "tableofcontents", "table-of-contents",
            "table-des-matieres",
        } for name in (values.get("id", "").lower(),)):
            self.skip_stack.append(tag)
            self.stats.toc_entries_removed += 1
            return
        if tag == "title" or tag in {"meta", "base", "link"}:
            return
        if "title-page" in classes:
            self.skip_stack.append(tag)
            self.stats.dropped_tags += 1
            return
        if tag in DROP_WITH_CONTENT:
            self.skip_stack.append(tag)
            self.stats.dropped_tags += 1
            return
        if not self.in_body and self.body_seen:
            return
        if tag in {"a", "span", "font"}:
            if tag == "a":
                self.stats.links_unwrapped += 1
            elif tag == "span":
                self.stats.spans_unwrapped += 1
            return
        if tag == "hr":
            self.stats.dropped_tags += 1
            return
        if tag not in ALLOWED_TAGS:
            return

        output_attrs: list[tuple[str, str]] = []
        if tag == "p":
            style = values.get("style", "").lower()
            align = values.get("align", "").lower()
            if align == "right" or re.search(r"text-align\s*:\s*right", style):
                output_attrs.append(("class", "align-right"))
            elif align == "center" or re.search(r"text-align\s*:\s*center", style):
                output_attrs.append(("class", "align-center"))
            else:
                safe = [item for item in values.get("class", "").split()
                        if item in KEEP_CLASSES]
                if safe:
                    output_attrs.append(("class", " ".join(safe)))
            self.paragraphs.append({"tag": tag, "start": len(self.output),
                                    "empty_counted": False})
        elif tag == "img":
            self.stats.images_removed += 1
            return
        elif "class" in values:
            safe = [item for item in values["class"].split() if item in KEEP_CLASSES]
            if safe:
                output_attrs.append(("class", " ".join(safe)))

        self.stats.attributes_removed += sum(
            1 for name, _ in attrs
            if name.lower() not in {key for key, _ in output_attrs}
        )
        attrs_html = "".join(f' {name}="{html.escape(value, quote=True)}"'
                             for name, value in output_attrs)
        self.output.append(f"<{tag}{attrs_html}>")
        if tag in {"p", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.text_elements.append({"tag": tag, "start": len(self.output) - 1,
                                       "text": ""})
        if tag not in VOID_TAGS:
            self.tag_stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.drop_footer:
            return
        for capture in reversed(self.captures):
            if capture["tag"] == tag:
                key = capture["key"]
                value = re.sub(r"\s+", " ", capture["value"]).strip()
                if value and key not in self.metadata:
                    self.metadata[key] = value
                self.captures.remove(capture)
                break

        if self.skip_stack:
            for index in range(len(self.skip_stack) - 1, -1, -1):
                if self.skip_stack[index] == tag:
                    del self.skip_stack[index:]
                    break
            return
        if tag == "body":
            self.in_body = False
            self.was_body = True
            return
        if tag == "head":
            self.in_head = False
            return
        if tag in {"html", "head"}:
            return
        if not self.in_body and self.body_seen:
            return
        if tag == "title" or tag in {"a", "span", "font", "hr"} or tag not in ALLOWED_TAGS:
            return
        if tag in VOID_TAGS:
            return

        element = next((item for item in reversed(self.text_elements)
                        if item["tag"] == tag), None)
        if element is not None:
            self.text_elements.remove(element)
            normalized = normalize_words(str(element["text"]))
            is_toc_heading = normalized in {
                "table des matieres", "sommaire", "table of contents", "contents",
            }
            is_publication_note = "ebooks libres et gratuits" in normalized
            is_publication_note = is_publication_note or (
                "publication par le groupe" in normalized
                or "publication du groupe" in normalized
            )
            is_publication_section = (
                tag in {"p", "h1", "h2", "h3", "h4", "h5", "h6"}
                and normalized == "a propos de cette edition electronique"
            )
            if is_toc_heading or is_publication_note or is_publication_section:
                start = int(element["start"])
                del self.output[start:]
                stack_index = next((i for i in range(len(self.tag_stack) - 1, -1, -1)
                                    if self.tag_stack[i] == tag), None)
                if stack_index is not None:
                    del self.tag_stack[stack_index:]
                if tag == "p" and self.paragraphs:
                    self.paragraphs.pop()
                if is_toc_heading:
                    self.stats.toc_sections_removed += 1
                else:
                    self.stats.publication_mentions_removed += 1
                if is_publication_section:
                    self.drop_footer = True
                return

        stack_index = next((i for i in range(len(self.tag_stack) - 1, -1, -1)
                            if self.tag_stack[i] == tag), None)
        if stack_index is None:
            return
        while len(self.tag_stack) > stack_index:
            closing = self.tag_stack.pop()
            self.output.append(f"</{closing}>")
            if closing == "p" and self.paragraphs:
                paragraph = self.paragraphs.pop()
                start = int(paragraph["start"])
                inner = "".join(self.output[start + 1:-1])
                if not re.sub(r"<br\s*/?>|&nbsp;|\s", "", inner, flags=re.I):
                    del self.output[start:]
                    self.stats.empty_paragraphs += 1
                    if not self._ends_with_stanza_break():
                        self.output.append('<p class="stanza-break"></p>')

    def handle_data(self, data: str) -> None:
        if self.drop_footer or self.skip_stack:
            return
        for capture in self.captures:
            capture["value"] += data
        for element in self.text_elements:
            element["text"] = str(element["text"]) + data
        if self.in_head:
            return
        if self.body_seen and not self.in_body:
            return
        clean_text, removed = remove_urls(data)
        self.stats.urls_removed += removed
        self.output.append(html.escape(clean_text, quote=False))

    def handle_entityref(self, name: str) -> None:
        self.handle_data(html.unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self.handle_data(html.unescape(f"&#{name};"))

    def handle_comment(self, data: str) -> None:
        self.stats.comments_removed += 1

    def _ends_with_stanza_break(self) -> bool:
        return bool(self.output and self.output[-1] == '<p class="stanza-break"></p>')

    def finish(self) -> str:
        while self.tag_stack:
            self.output.append(f"</{self.tag_stack.pop()}>")
        content = "".join(self.output).strip()
        content, removed_urls = remove_urls(content)
        self.stats.urls_removed += removed_urls
        return re.sub(r"(?:<p class=\"stanza-break\"></p>\s*){2,}",
                      '<p class="stanza-break"></p>\n', content)


def decode_html(data: bytes) -> str:
    """Decode common manuscript encodings without losing accented French text."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


URL_PATTERN = re.compile(
    r"(?i)(?:(?:https?|ftp)\s*:\s*(?:/\s*){0,2}|/{1,2}\s*)?"
    r"(?:www\s*\.\s*)?"
    r"[a-z0-9][a-z0-9-]*(?:\s*\.\s*[a-z0-9-]+)*\s*\.\s*"
    r"(?:com|org|net|fr|edu|gov|info|biz|eu|co|io|uk|de|ch|ca|be|us|xyz)\b"
    r"(?:\s*/[^\s<>\"']*)?"
)


def normalize_words(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    unaccented = "".join(char for char in decomposed
                         if not unicodedata.combining(char))
    return re.sub(r"[^\w]+", " ", unaccented).strip()


def remove_urls(text: str) -> tuple[str, int]:
    """Remove visible web addresses, keeping punctuation that follows them."""
    removed = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal removed
        value = match.group(0)
        address = value.rstrip(".,;:!?)]}")
        if address:
            removed += 1
            return value[len(address):]
        return value

    return URL_PATTERN.sub(replace, text), removed


def load_source(path: Path) -> str:
    """Read plain HTML or extract only the HTML part from a Blink MHTML save."""
    raw = path.read_bytes()
    if not raw.lstrip().startswith(b"From: <Saved by Blink>"):
        return decode_html(raw)

    # Blink MHTML sometimes indents MIME header lines with tabs. The email
    # parser treats those as folded headers, so unindent known header names.
    raw = re.sub(
        rb"(?m)^[ \t]+(?=(?:From:|Snapshot-Content-Location:|Subject:|Date:|"
        rb"MIME-Version:|Content-Type:|Content-ID:|Content-Transfer-Encoding:|"
        rb"Content-Location:|[-]{2,}MultipartBoundary))",
        b"",
        raw,
    )
    message = BytesParser(policy=policy.default).parsebytes(raw)
    html_part = next((part for part in message.walk()
                      if part.get_content_type() == "text/html"), None)
    if html_part is None:
        raise ValueError("archive Web sans partie text/html")
    html_bytes = html_part.get_payload(decode=True) or b""
    charset = html_part.get_content_charset() or "utf-8"
    try:
        return html_bytes.decode(charset, errors="replace")
    except LookupError:
        return decode_html(html_bytes)


def wrap_document(title: str, author: str, year: str, body: str) -> str:
    title_text = html.escape(title or "Sans titre")
    author_text = html.escape(author or "Victor Hugo")
    year_text = html.escape(year.strip(" ()"))
    year_block = f'\n    <p class="book-year">({year_text})</p>' if year_text else ""
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>{title_text} — {author_text}</title>
  <style>
{KDP_CSS}
  </style>
</head>
<body>
  <div class="title-page">
    <p class="book-author">{author_text}</p>
    <h1 class="book-title">{title_text}</h1>{year_block}
  </div>
  <div class="novel-body">
{body}
  </div>
</body>
</html>
"""


def clean_file(source_path: Path, output_path: Path) -> CleanStats:
    source = load_source(source_path)
    cleaner = BookCleaner()
    cleaner.feed(source)
    body = cleaner.finish()

    title = cleaner.metadata.get("book_title") or source_path.stem
    author = cleaner.metadata.get("author") or "Victor Hugo"
    year = cleaner.metadata.get("year", "")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(wrap_document(title, author, year, body), encoding="utf-8")
    return cleaner.stats


def default_paths() -> tuple[Path, Path]:
    root = Path(__file__).resolve().parent
    input_dir = root / "victor-hugo"
    return input_dir, input_dir / "cleaned"


def main(argv: list[str] | None = None) -> int:
    default_input, default_output = default_paths()
    parser = argparse.ArgumentParser(
        description="Nettoie tous les fichiers HTML d’un dossier pour un intérieur KDP."
    )
    parser.add_argument("--input-dir", type=Path, default=default_input,
                        help=f"Dossier source (défaut : {default_input})")
    parser.add_argument("--output-dir", type=Path, default=default_output,
                        help=f"Dossier de sortie (défaut : {default_output})")
    args = parser.parse_args(argv)
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    if not input_dir.is_dir():
        parser.error(f"Dossier source introuvable : {input_dir}")
    if input_dir == output_dir:
        parser.error("Le dossier de sortie doit être différent du dossier source.")

    sources = sorted((p for p in input_dir.glob("*.html") if p.is_file()),
                     key=lambda p: p.name.casefold())
    sources += sorted((p for p in input_dir.glob("*.htm") if p.is_file()),
                      key=lambda p: p.name.casefold())
    if not sources:
        print(f"Aucun fichier .html ou .htm trouvé dans : {input_dir}")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Nettoyage de {len(sources)} fichiers HTML")
    print(f"Originaux conservés dans : {input_dir}")
    print(f"Résultats enregistrés dans : {output_dir}\n")
    failures = 0
    for source_path in sources:
        output_path = output_dir / f"{source_path.stem}.html"
        try:
            stats = clean_file(source_path, output_path)
            notes = []
            if stats.images_removed:
                notes.append(f"{stats.images_removed} image(s) supprimée(s)")
            if stats.urls_removed:
                notes.append(f"{stats.urls_removed} URL supprimée(s)")
            if stats.toc_sections_removed or stats.toc_entries_removed:
                notes.append(
                    f"table des matières retirée "
                    f"({stats.toc_entries_removed} entrée(s))"
                )
            if stats.publication_mentions_removed:
                notes.append(
                    f"{stats.publication_mentions_removed} mention(s) éditoriale(s) retirée(s)"
                )
            summary = ", ".join(notes) or "texte et structure nettoyés"
            print(f"OK  {source_path.name} -> {output_path.name} ({summary})")
        except Exception as error:  # Continue so one malformed book cannot stop the batch.
            failures += 1
            print(f"ERREUR  {source_path.name}: {error}", file=sys.stderr)

    print(f"\nTerminé : {len(sources) - failures}/{len(sources)} fichier(s) nettoyé(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
