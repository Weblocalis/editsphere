#!/usr/bin/env python3
"""
Clean and format HTML documents for Amazon KDP print-on-demand (6" x 9").
Strictly print-ready without non-printable tags, anchors, or interactive elements.
Supports QUATREVINGT-TREIZE.html and les-contemplations.html.
"""

import os
import re
import subprocess
import urllib.request

KDP_CSS = """\
		/* Configuration de la page pour impression Amazon KDP roman 6" x 9" (152,4 mm x 228,6 mm) */
		@page {
			size: 6in 9in;
			margin-top: 20mm;
			margin-bottom: 20mm;
			margin-inside: 22mm;  /* Petit fond (reliure) */
			margin-outside: 16mm; /* Grand fond */
		}

		@page :left {
			margin-left: 16mm;
			margin-right: 22mm;
		}

		@page :right {
			margin-left: 22mm;
			margin-right: 16mm;
		}

		html {
			font-size: 11pt;
			line-height: 1.45;
			-webkit-text-size-adjust: 100%;
		}

		body {
			font-family: "Georgia", "Garamond", "Times New Roman", serif;
			color: #111111;
			background: #ffffff;
			margin: 0;
			padding: 0;
			text-rendering: optimizeLegibility;
		}

		/* Typographie du texte de fiction / poésie */
		p {
			margin: 0;
			text-indent: 1.5em;
			text-align: justify;
			hyphens: auto;
			-webkit-hyphens: auto;
			orphans: 2;
			widows: 2;
		}

		/* Premier paragraphe après un titre : pas d'alinéa */
		h1 + p, h2 + p, h3 + p, h4 + p, h5 + p {
			text-indent: 0;
		}

		/* Alignement à droite pour les dates, lieux et signatures */
		p.align-right {
			text-align: right;
			text-indent: 0;
			margin-top: 0.5em;
			margin-bottom: 0.5em;
			font-style: italic;
			font-size: 0.9em;
		}

		/* Saut de strophe en poésie */
		p.stanza-break {
			margin: 0;
			height: 0.9em;
			text-indent: 0;
		}

		/* Page de titre */
		.title-page {
			page-break-after: always;
			break-after: page;
			text-align: center;
			padding-top: 25%;
			min-height: 70vh;
		}

		.title-page .book-author {
			font-size: 1.6rem;
			letter-spacing: 0.15em;
			text-transform: uppercase;
			margin-bottom: 2rem;
			text-indent: 0;
			text-align: center;
		}

		.title-page .book-title {
			font-size: 2.2rem;
			font-weight: bold;
			letter-spacing: 0.1em;
			line-height: 1.2;
			margin: 2rem 0;
			page-break-before: avoid;
			break-before: avoid;
		}

		.title-page .book-year {
			font-size: 1.1rem;
			color: #555555;
			margin-top: 3rem;
			text-indent: 0;
			text-align: center;
		}

		/* Titres des divisions */
		h1, h2, h3, h4, h5 {
			text-align: center;
			font-weight: normal;
			page-break-after: avoid;
			break-after: avoid;
		}

		h1 {
			page-break-before: always;
			break-before: page;
			font-size: 1.8rem;
			letter-spacing: 0.08em;
			margin-top: 30%;
			margin-bottom: 2rem;
			text-transform: uppercase;
		}

		h2 {
			page-break-before: always;
			break-before: page;
			font-size: 1.4rem;
			letter-spacing: 0.06em;
			margin-top: 20%;
			margin-bottom: 1.5rem;
			text-transform: uppercase;
		}

		h3 {
			font-size: 1.15rem;
			letter-spacing: 0.04em;
			margin-top: 2rem;
			margin-bottom: 1rem;
		}

		h4 {
			font-size: 1.05rem;
			letter-spacing: 0.02em;
			margin-top: 1.5rem;
			margin-bottom: 0.8rem;
		}

		h5 {
			font-size: 1rem;
			letter-spacing: 0.05em;
			margin-top: 1.2rem;
			margin-bottom: 0.6rem;
			font-weight: bold;
		}

		/* Notes de bas de page */
		sup.footnote-ref {
			font-size: 0.75em;
			vertical-align: super;
			line-height: 0;
		}

		.footnotes-section {
			page-break-before: always;
			break-before: page;
			margin-top: 3rem;
			padding-top: 1.5rem;
			border-top: 1px solid #ccc;
		}

		.footnotes-section h2 {
			margin-top: 0;
			page-break-before: avoid;
			break-before: avoid;
		}

		.footnote-text {
			font-size: 0.85rem;
			line-height: 1.35;
			margin-bottom: 0.6rem;
			text-indent: 0;
		}

		.footnote-num {
			font-weight: bold;
			margin-right: 0.3em;
		}
"""


def clean_contemplations(output_path='les-contemplations.html'):
    """Clean and format LES CONTEMPLATIONS for Amazon KDP print-on-demand (6" x 9")."""
    url = 'https://www.ebooksgratuits.com/html/hugo_contemplations.html'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        orig_content = resp.read().decode('utf-8')

    # Locate preface h1 (first h1 of the actual work, skipping table of contents)
    pref_idx = orig_content.find('PRÉFACE</span></a></h1>')
    if pref_idx == -1:
        raise ValueError("Could not find PRÉFACE heading in source HTML")
    h1_idx = orig_content.rfind('<h1', 0, pref_idx)

    # Locate end of work (before Ebooks libres et gratuits postface)
    end_marker = orig_content.find('À propos de cette édition électronique')
    if end_marker == -1:
        raise ValueError("Could not find end of work marker")
    p_end = orig_content.rfind('<p', 0, end_marker)

    work_html = orig_content[h1_idx:p_end]

    def is_empty_p(p_inner):
        text = re.sub(r'<[^>]+>', '', p_inner)
        text = text.replace('&nbsp;', ' ').strip()
        return len(text) == 0

    text = work_html

    # Remove all <a> and </a> tags completely
    text = re.sub(r'</?a[^>]*>', '', text)

    # Remove stray page breaks, hr, div
    text = re.sub(r'<br clear="?all"?[^>]*>', '', text, flags=re.I)
    text = re.sub(r'<hr[^>]*>', '', text, flags=re.I)
    text = re.sub(r'</?div[^>]*>', '', text, flags=re.I)

    # Remove all span tags
    text = re.sub(r'</?span[^>]*>', '', text)

    # Clean headings: remove any attributes, preserve <br> lines
    def clean_heading(m):
        tag = m.group(1)
        inner = m.group(2)
        clean_inner = re.sub(r'<br\s*/?>', '<br>', inner, flags=re.I)
        lines = [line.strip() for line in clean_inner.split('<br>') if line.strip()]
        heading_text = '<br>'.join(lines)
        return f'<{tag}>{heading_text}</{tag}>'

    text = re.sub(r'<(h[1-5])[^>]*>(.*?)</\1>', clean_heading, text, flags=re.S)

    # Tokenize headings and paragraphs in proper order
    block_pattern = re.compile(r'(<(?:h[1-5])>.*?</(?:h[1-5])>|<p(?:\s+[^>]*)?>.*?</p>)', re.S)

    cleaned_blocks = []
    prev_was_empty = False
    prev_was_heading = False

    for match in block_pattern.finditer(text):
        block = match.group(1).strip()
        if block.startswith('<h'):
            cleaned_blocks.append(block)
            prev_was_heading = True
            prev_was_empty = False
        elif block.startswith('<p'):
            align_right = ('align=right' in block or 'align="right"' in block or 'text-align:right' in block)
            inner = re.sub(r'^<p(?:\s+[^>]*)?>|</p>$', '', block, flags=re.S).strip()
            if is_empty_p(inner):
                if not prev_was_empty and not prev_was_heading:
                    cleaned_blocks.append('<p class="stanza-break"></p>')
                    prev_was_empty = True
            else:
                inner = re.sub(r'\s+', ' ', inner).strip()
                prev_was_empty = False
                prev_was_heading = False
                if align_right:
                    cleaned_blocks.append(f'<p class="align-right">{inner}</p>')
                else:
                    cleaned_blocks.append(f'<p>{inner}</p>')

    while cleaned_blocks and cleaned_blocks[-1] == '<p class="stanza-break"></p>':
        cleaned_blocks.pop()

    title_page_html = """\
\t<div class="title-page">
\t\t<p class="book-author">Victor Hugo</p>
\t\t<h1 class="book-title">LES CONTEMPLATIONS</h1>
\t\t<p class="book-year">(1856)</p>
\t</div>
"""

    novel_body_html = "\n".join(f"\t{block}" for block in cleaned_blocks)

    final_html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
\t<meta charset="UTF-8">
\t<title>LES CONTEMPLATIONS - Victor Hugo</title>
\t<style>
{KDP_CSS}
\t</style>
</head>
<body>

{title_page_html}
<div class="novel-body">
{novel_body_html}
</div>

</body>
</html>
"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_html)

    print(f"Successfully cleaned and generated {output_path}")


def clean_quatrevingt_treize(output_path='quatrevingt-treize.html'):
    """Clean and format QUATREVINGT-TREIZE for Amazon KDP print-on-demand (6" x 9")."""
    # Fetch from local file or initial git state if available
    if os.path.exists('quatrevingt-treize.html'):
        with open('quatrevingt-treize.html', 'r', encoding='utf-8') as f:
            content = f.read()
        if '<div class="novel-body">' in content:
            print("quatrevingt-treize.html is already cleaned.")
            return

    try:
        orig_content = subprocess.check_output(['git', 'show', '3b08562:QUATREVINGT-TREIZE.html']).decode('utf-8', errors='ignore')
    except Exception:
        with open('quatrevingt-treize.html', 'r', encoding='utf-8') as f:
            orig_content = f.read()

    h1_idx = orig_content.find('<h1>')
    if h1_idx == -1:
        raise ValueError("Could not find first <h1> tag")

    body_and_notes = orig_content[h1_idx:]

    fn_idx = body_and_notes.find('<div id="ftn1">')
    if fn_idx != -1:
        novel_content = body_and_notes[:fn_idx]
        footnotes_content = body_and_notes[fn_idx:]
    else:
        novel_content = body_and_notes
        footnotes_content = ""

    footnotes = []
    if footnotes_content:
        for m in re.finditer(r'<div id="ftn(\d+)">(.*?)</div>', footnotes_content, re.S):
            fn_id = m.group(1)
            fn_body = m.group(2)
            fn_body = re.sub(r'</?span[^>]*>', '', fn_body)
            fn_body = re.sub(r'</?a[^>]*>', '', fn_body)
            fn_body = re.sub(r'<p[^>]*>', f'<p class="footnote-text"><span class="footnote-num">[{fn_id}]</span> ', fn_body)
            fn_body = re.sub(r'\s+', ' ', fn_body).strip()
            footnotes.append(fn_body)

    def is_empty_p(p_inner):
        text = re.sub(r'<[^>]+>', '', p_inner)
        text = text.replace('&nbsp;', ' ').strip()
        return len(text) == 0

    text = novel_content

    def replace_ftn_ref(m):
        full = m.group(0)
        num_m = re.search(r'#_ftn(\d+)', full)
        if num_m:
            num = num_m.group(1)
            return f'<sup class="footnote-ref">[{num}]</sup>'
        return ''

    text = re.sub(r'<a\s+[^>]*href=[\'"][^\'"]*#_ftn\d+[\'"][^>]*>.*?</a>', replace_ftn_ref, text, flags=re.S)
    text = re.sub(r'</?a[^>]*>', '', text)
    text = re.sub(r'<br clear="?all"?[^>]*>', '', text, flags=re.I)
    text = re.sub(r'<hr[^>]*>', '', text, flags=re.I)
    text = re.sub(r'</?div[^>]*>', '', text, flags=re.I)
    text = re.sub(r'</?span[^>]*>', '', text)

    def clean_heading(m):
        tag = m.group(1)
        inner = m.group(2)
        clean_inner = re.sub(r'<br\s*/?>', '<br>', inner, flags=re.I)
        lines = [line.strip() for line in clean_inner.split('<br>') if line.strip()]
        heading_text = '<br>'.join(lines)
        return f'<{tag}>{heading_text}</{tag}>'

    text = re.sub(r'<(h[1-4])[^>]*>(.*?)</\1>', clean_heading, text, flags=re.S)

    block_pattern = re.compile(r'(<(?:h[1-4])>.*?</(?:h[1-4])>|<p(?:\s+[^>]*)?>.*?</p>)', re.S)

    cleaned_blocks = []
    for match in block_pattern.finditer(text):
        block = match.group(1).strip()
        if block.startswith('<h'):
            cleaned_blocks.append(block)
        elif block.startswith('<p'):
            inner = re.sub(r'^<p(?:\s+[^>]*)?>|</p>$', '', block, flags=re.S).strip()
            if not is_empty_p(inner):
                inner = re.sub(r'\s+', ' ', inner).strip()
                cleaned_blocks.append(f'<p>{inner}</p>')

    title_page_html = """\
\t<div class="title-page">
\t\t<p class="book-author">Victor Hugo</p>
\t\t<h1 class="book-title">QUATREVINGT-TREIZE</h1>
\t\t<p class="book-year">(1873)</p>
\t</div>
"""

    footnotes_section_html = ""
    if footnotes:
        fn_items = "\n".join(f"\t\t{fn}" for fn in footnotes)
        footnotes_section_html = f"""\
\t<div class="footnotes-section">
\t\t<h2>Notes</h2>
{fn_items}
\t</div>
"""

    novel_body_html = "\n".join(f"\t{block}" for block in cleaned_blocks)

    final_html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
\t<meta charset="UTF-8">
\t<title>QUATREVINGT-TREIZE - Victor Hugo</title>
\t<style>
{KDP_CSS}
\t</style>
</head>
<body>

{title_page_html}
<div class="novel-body">
{novel_body_html}
</div>

{footnotes_section_html}
</body>
</html>
"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_html)

    print(f"Successfully cleaned and generated {output_path}")


if __name__ == '__main__':
    clean_contemplations('les-contemplations.html')
