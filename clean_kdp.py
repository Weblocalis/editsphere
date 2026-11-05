#!/usr/bin/env python3
"""
Clean and format QUATREVINGT-TREIZE.html for Amazon KDP print-on-demand (6" x 9").
"""

import re

def clean_html(input_path, output_path):
    with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # 1. Locate the main sections
    # Find the first <h1> which marks the start of the novel body (after title & TOC)
    h1_idx = content.find('<h1>')
    if h1_idx == -1:
        raise ValueError("Could not find first <h1> tag")

    # Everything after first <h1> until footnotes
    body_and_notes = content[h1_idx:]

    # Footnotes separator
    fn_idx = body_and_notes.find('<div id="ftn1">')
    if fn_idx != -1:
        novel_content = body_and_notes[:fn_idx]
        footnotes_content = body_and_notes[fn_idx:]
    else:
        novel_content = body_and_notes
        footnotes_content = ""

    # 2. Extract footnotes cleanly
    # Pattern for each footnote: <div id="ftn(\d+)">...</div>
    footnotes = []
    if footnotes_content:
        for m in re.finditer(r'<div id="ftn(\d+)">(.*?)</div>', footnotes_content, re.S):
            fn_id = m.group(1)
            fn_body = m.group(2)
            # Remove Mso classes, spans, external links from footnote
            # Find the text of footnote
            # The structure is: <p class="MsoFootnoteText"><a href="...#_ftnrefN" ...>[N]</a>...text...</p>
            # We want: <p id="ftnN"><a href="#ftnrefN" class="footnote-back">[N]</a> Text...</p>
            # Remove any span tags
            fn_body = re.sub(r'</?span[^>]*>', '', fn_body)
            # Clean anchor href
            fn_body = re.sub(r'<a\s+[^>]*href=[\'"][^\'"]*#_ftnref(\d+)[\'"][^>]*>(.*?)</a>',
                             r'<a href="#ftnref\1" class="footnote-back">\2</a>', fn_body, flags=re.S)
            # Clean p tag
            fn_body = re.sub(r'<p[^>]*>', f'<p id="ftn{fn_id}" class="footnote-text">', fn_body)
            # Remove extraneous newlines/spaces
            fn_body = re.sub(r'\s+', ' ', fn_body).strip()
            footnotes.append(fn_body)

    # 3. Clean the novel content
    # Remove all useless empty paragraphs: <p ...>(?:\s|&nbsp;|<span[^>]*>|</span>)*</p>
    def is_empty_p(p_inner):
        text = re.sub(r'<[^>]+>', '', p_inner)
        text = text.replace('&nbsp;', ' ').strip()
        return len(text) == 0

    # Let's clean paragraphs and headings in novel_content
    # First normalize newlines
    text = novel_content

    # Remove OLE_LINK anchors
    text = re.sub(r'<a name="OLE_LINK\d+"></a>', '', text)
    text = re.sub(r'<a name="OLE_LINK\d+">', '', text)

    # Clean footnote reference calls in novel text:
    # e.g.: <a href="...#_ftn1" name="_ftnref1" ...><span ...>[1]...</span></a>
    def replace_ftn_ref(m):
        full = m.group(0)
        num_m = re.search(r'#_ftn(\d+)', full)
        if num_m:
            num = num_m.group(1)
            return f'<sup class="footnote-ref"><a href="#ftn{num}" id="ftnref{num}">[{num}]</a></sup>'
        return full

    text = re.sub(r'<a\s+[^>]*href=[\'"][^\'"]*#_ftn\d+[\'"][^>]*>.*?</a>', replace_ftn_ref, text, flags=re.S)

    # Remove any stray page breaks or <br clear="all"...>
    text = re.sub(r'<br clear="?all"?[^>]*>', '', text, flags=re.I)
    text = re.sub(r'<hr[^>]*>', '', text, flags=re.I)
    text = re.sub(r'<div[^>]*>', '', text, flags=re.I)
    text = re.sub(r'</div>', '', text, flags=re.I)

    # Remove all <span> and </span> tags
    text = re.sub(r'</?span[^>]*>', '', text)

    # Remove all numbered anchor markers like <a name="1">
    text = re.sub(r'<a name=\"\d+\">', '', text)

    # Clean <a> anchors inside headings (like <a name="_Toc125052816">)
    # We can keep an id on the heading for potential navigation
    def clean_heading(m):
        tag = m.group(1)
        inner = m.group(2)
        # extract Toc anchor name if any
        toc_m = re.search(r'name=\"([^\"]+)\"', inner)
        toc_id = f' id="{toc_m.group(1)}"' if toc_m else ''
        # strip tags inside heading except <br>
        # but replace <br> with a single <br>
        clean_inner = re.sub(r'<a[^>]*>', '', inner)
        clean_inner = re.sub(r'</a>', '', clean_inner)
        clean_inner = re.sub(r'<br\s*/?>', '<br>', clean_inner, flags=re.I)
        # clean whitespace
        lines = [line.strip() for line in clean_inner.split('<br>') if line.strip()]
        heading_text = '<br>'.join(lines)
        return f'<{tag}{toc_id}>{heading_text}</{tag}>'

    text = re.sub(r'<(h[1-4])[^>]*>(.*?)</\1>', clean_heading, text, flags=re.S)

    # Now handle all <p ...>...</p> tags
    # Parse paragraphs
    p_pattern = re.compile(r'<p(?:\s+[^>]*)?>(.*?)</p>', re.S)

    clean_paragraphs = []
    for m in p_pattern.finditer(text):
        p_body = m.group(1).strip()
        if is_empty_p(p_body):
            continue
        # Clean any remaining internal redundant spaces/newlines
        # Preserve <i>, <b>, <a>, <sup>
        # Replace multiple spaces/newlines with a single space
        p_body = re.sub(r'\s+', ' ', p_body).strip()
        clean_paragraphs.append(f'<p>{p_body}</p>')

    # We need to assemble headings and paragraphs in proper order.
    # Rather than parsing p's separately, let's tokenize the flow:
    # A regex that matches either a heading <h[1-4]...</h[1-4]> or a paragraph <p...</p>
    block_pattern = re.compile(r'(<(?:h[1-4])[^>]*>.*?</(?:h[1-4])>|<p(?:\s+[^>]*)?>.*?</p>)', re.S)

    cleaned_blocks = []
    for match in block_pattern.finditer(text):
        block = match.group(1).strip()
        if block.startswith('<h'):
            cleaned_blocks.append(block)
        elif block.startswith('<p'):
            # check if empty
            inner = re.sub(r'^<p(?:\s+[^>]*)?>|</p>$', '', block, flags=re.S).strip()
            if not is_empty_p(inner):
                inner = re.sub(r'\s+', ' ', inner).strip()
                cleaned_blocks.append(f'<p>{inner}</p>')

    # 4. Construct Title Page
    title_page_html = """\
\t<section class="title-page">
\t\t<p class="book-author">Victor Hugo</p>
\t\t<h1 class="book-title">QUATREVINGT-TREIZE</h1>
\t\t<p class="book-year">(1873)</p>
\t</section>
"""

    # 5. Footnotes section HTML
    footnotes_section_html = ""
    if footnotes:
        fn_items = "\n".join(f"\t\t{fn}" for fn in footnotes)
        footnotes_section_html = f"""\
\t<section class="footnotes-section">
\t\t<h2>Notes</h2>
{fn_items}
\t</section>
"""

    # 6. Build the novel body HTML
    novel_body_html = "\n".join(f"\t{block}" for block in cleaned_blocks)

    # 7. Complete HTML document with Amazon KDP 6"x9" CSS
    css_content = """\
\t\t@charset "UTF-8";

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

\t\tsup.footnote-ref a {
\t\t\tcolor: inherit;
\t\t\ttext-decoration: none;
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

\t\t.footnote-back {
\t\t\tfont-weight: bold;
\t\t\tcolor: inherit;
\t\t\ttext-decoration: none;
\t\t\tmargin-right: 0.3em;
\t\t}

\t\ta {
\t\t\tcolor: inherit;
\t\t\ttext-decoration: none;
\t\t}
"""

    final_html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
\t<meta charset="UTF-8">
\t<meta name="viewport" content="width=device-width, initial-scale=1.0">
\t<title>QUATREVINGT-TREIZE - Victor Hugo</title>
\t<style>
{css_content}
\t</style>
</head>
<body>

{title_page_html}
<main>
{novel_body_html}
</main>

{footnotes_section_html}
</body>
</html>
"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_html)

    print(f"Successfully cleaned and generated {output_path}")

if __name__ == '__main__':
    clean_html('QUATREVINGT-TREIZE.html', 'QUATREVINGT-TREIZE.html.clean')
