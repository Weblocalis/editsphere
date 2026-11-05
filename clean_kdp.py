#!/usr/bin/env python3
"""
Clean and format QUATREVINGT-TREIZE.html for Amazon KDP print-on-demand (6" x 9").
Strictly print-ready without non-printable tags, anchors, or interactive elements.
"""

import re
import subprocess

def clean_html(output_path):
    # Fetch original file from initial commit in git to work from original ground truth
    orig_content = subprocess.check_output(['git', 'show', '3b08562:QUATREVINGT-TREIZE.html']).decode('utf-8', errors='ignore')

    # 1. Locate the main sections
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

    # 2. Extract footnotes cleanly (for print: no <a> link, just bold [N])
    footnotes = []
    if footnotes_content:
        for m in re.finditer(r'<div id="ftn(\d+)">(.*?)</div>', footnotes_content, re.S):
            fn_id = m.group(1)
            fn_body = m.group(2)
            # Remove any span and a tags
            fn_body = re.sub(r'</?span[^>]*>', '', fn_body)
            fn_body = re.sub(r'</?a[^>]*>', '', fn_body)
            # Clean p tag
            fn_body = re.sub(r'<p[^>]*>', f'<p class="footnote-text"><span class="footnote-num">[{fn_id}]</span> ', fn_body)
            fn_body = re.sub(r'\s+', ' ', fn_body).strip()
            footnotes.append(fn_body)

    # 3. Clean the novel content
    def is_empty_p(p_inner):
        text = re.sub(r'<[^>]+>', '', p_inner)
        text = text.replace('&nbsp;', ' ').strip()
        return len(text) == 0

    text = novel_content

    # Remove all anchor tags <a ...>...</a> or just <a>
    # For footnote references in novel: replace <a ...>[N]...</a> with <sup class="footnote-ref">[{N}]</sup>
    def replace_ftn_ref(m):
        full = m.group(0)
        num_m = re.search(r'#_ftn(\d+)', full)
        if num_m:
            num = num_m.group(1)
            return f'<sup class="footnote-ref">[{num}]</sup>'
        return ''

    text = re.sub(r'<a\s+[^>]*href=[\'"][^\'"]*#_ftn\d+[\'"][^>]*>.*?</a>', replace_ftn_ref, text, flags=re.S)

    # Remove all remaining <a> and </a> tags completely
    text = re.sub(r'</?a[^>]*>', '', text)

    # Remove stray page breaks, hr, div
    text = re.sub(r'<br clear="?all"?[^>]*>', '', text, flags=re.I)
    text = re.sub(r'<hr[^>]*>', '', text, flags=re.I)
    text = re.sub(r'</?div[^>]*>', '', text, flags=re.I)

    # Remove all span tags
    text = re.sub(r'</?span[^>]*>', '', text)

    # Clean headings: remove any attributes (no id, no class)
    def clean_heading(m):
        tag = m.group(1)
        inner = m.group(2)
        clean_inner = re.sub(r'<br\s*/?>', '<br>', inner, flags=re.I)
        lines = [line.strip() for line in clean_inner.split('<br>') if line.strip()]
        heading_text = '<br>'.join(lines)
        return f'<{tag}>{heading_text}</{tag}>'

    text = re.sub(r'<(h[1-4])[^>]*>(.*?)</\1>', clean_heading, text, flags=re.S)

    # Tokenize headings and paragraphs in proper order
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

    # 4. Construct Title Page
    title_page_html = """\
\t<div class="title-page">
\t\t<p class="book-author">Victor Hugo</p>
\t\t<h1 class="book-title">QUATREVINGT-TREIZE</h1>
\t\t<p class="book-year">(1873)</p>
\t</div>
"""

    # 5. Footnotes section HTML
    footnotes_section_html = ""
    if footnotes:
        fn_items = "\n".join(f"\t\t{fn}" for fn in footnotes)
        footnotes_section_html = f"""\
\t<div class="footnotes-section">
\t\t<h2>Notes</h2>
{fn_items}
\t</div>
"""

    # 6. Build the novel body HTML
    novel_body_html = "\n".join(f"\t{block}" for block in cleaned_blocks)

    # 7. Complete HTML document with Amazon KDP 6"x9" CSS
    css_content = """\
\t\t/* Configuration de la page pour impression Amazon KDP roman 6" x 9" (152,4 mm x 228,6 mm) */
\t\t@page {
\t\t\tsize: 6in 9in;
\t\t\tmargin-top: 20mm;
\t\t\tmargin-bottom: 20mm;
\t\t\tmargin-inside: 22mm;  /* Petit fond (reliure) */
\t\t\tmargin-outside: 16mm; /* Grand fond */
\t\t}

\t\t@page :left {
\t\t\tmargin-left: 16mm;
\t\t\tmargin-right: 22mm;
\t\t}

\t\t@page :right {
\t\t\tmargin-left: 22mm;
\t\t\tmargin-right: 16mm;
\t\t}

\t\thtml {
\t\t\tfont-size: 11pt;
\t\t\tline-height: 1.45;
\t\t\t-webkit-text-size-adjust: 100%;
\t\t}

\t\tbody {
\t\t\tfont-family: "Georgia", "Garamond", "Times New Roman", serif;
\t\t\tcolor: #111111;
\t\t\tbackground: #ffffff;
\t\t\tmargin: 0;
\t\t\tpadding: 0;
\t\t\ttext-rendering: optimizeLegibility;
\t\t}

\t\t/* Typographie du texte de fiction */
\t\tp {
\t\t\tmargin: 0;
\t\t\ttext-indent: 1.5em;
\t\t\ttext-align: justify;
\t\t\thyphens: auto;
\t\t\t-webkit-hyphens: auto;
\t\t\torphans: 2;
\t\t\twidows: 2;
\t\t}

\t\t/* Premier paragraphe après un titre : pas d'alinéa */
\t\th1 + p, h2 + p, h3 + p, h4 + p {
\t\t\ttext-indent: 0;
\t\t}

\t\t/* Page de titre */
\t\t.title-page {
\t\t\tpage-break-after: always;
\t\t\tbreak-after: page;
\t\t\ttext-align: center;
\t\t\tpadding-top: 25%;
\t\t\tmin-height: 70vh;
\t\t}

\t\t.title-page .book-author {
\t\t\tfont-size: 1.6rem;
\t\t\tletter-spacing: 0.15em;
\t\t\ttext-transform: uppercase;
\t\t\tmargin-bottom: 2rem;
\t\t\ttext-indent: 0;
\t\t\ttext-align: center;
\t\t}

\t\t.title-page .book-title {
\t\t\tfont-size: 2.2rem;
\t\t\tfont-weight: bold;
\t\t\tletter-spacing: 0.1em;
\t\t\tline-height: 1.2;
\t\t\tmargin: 2rem 0;
\t\t\tpage-break-before: avoid;
\t\t\tbreak-before: avoid;
\t\t}

\t\t.title-page .book-year {
\t\t\tfont-size: 1.1rem;
\t\t\tcolor: #555555;
\t\t\tmargin-top: 3rem;
\t\t\ttext-indent: 0;
\t\t\ttext-align: center;
\t\t}

\t\t/* Titres des divisions */
\t\th1, h2, h3, h4 {
\t\t\ttext-align: center;
\t\t\tfont-weight: normal;
\t\t\tpage-break-after: avoid;
\t\t\tbreak-after: avoid;
\t\t}

\t\th1 {
\t\t\tpage-break-before: always;
\t\t\tbreak-before: page;
\t\t\tfont-size: 1.8rem;
\t\t\tletter-spacing: 0.08em;
\t\t\tmargin-top: 30%;
\t\t\tmargin-bottom: 2rem;
\t\t\ttext-transform: uppercase;
\t\t}

\t\th2 {
\t\t\tpage-break-before: always;
\t\t\tbreak-before: page;
\t\t\tfont-size: 1.4rem;
\t\t\tletter-spacing: 0.06em;
\t\t\tmargin-top: 20%;
\t\t\tmargin-bottom: 1.5rem;
\t\t\ttext-transform: uppercase;
\t\t}

\t\th3 {
\t\t\tfont-size: 1.15rem;
\t\t\tletter-spacing: 0.04em;
\t\t\tmargin-top: 2rem;
\t\t\tmargin-bottom: 1rem;
\t\t}

\t\th4 {
\t\t\tfont-size: 1.05rem;
\t\t\tletter-spacing: 0.02em;
\t\t\tmargin-top: 1.5rem;
\t\t\tmargin-bottom: 0.8rem;
\t\t}

\t\t/* Notes de bas de page */
\t\tsup.footnote-ref {
\t\t\tfont-size: 0.75em;
\t\t\tvertical-align: super;
\t\t\tline-height: 0;
\t\t}

\t\t.footnotes-section {
\t\t\tpage-break-before: always;
\t\t\tbreak-before: page;
\t\t\tmargin-top: 3rem;
\t\t\tpadding-top: 1.5rem;
\t\t\tborder-top: 1px solid #ccc;
\t\t}

\t\t.footnotes-section h2 {
\t\t\tmargin-top: 0;
\t\t\tpage-break-before: avoid;
\t\t\tbreak-before: avoid;
\t\t}

\t\t.footnote-text {
\t\t\tfont-size: 0.85rem;
\t\t\tline-height: 1.35;
\t\t\tmargin-bottom: 0.6rem;
\t\t\ttext-indent: 0;
\t\t}

\t\t.footnote-num {
\t\t\tfont-weight: bold;
\t\t\tmargin-right: 0.3em;
\t\t}
"""

    final_html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
\t<meta charset="UTF-8">
\t<title>QUATREVINGT-TREIZE - Victor Hugo</title>
\t<style>
{css_content}
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
    clean_html('QUATREVINGT-TREIZE.html')
