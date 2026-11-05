#!/usr/bin/env python3
"""
Verification test suite for QUATREVINGT-TREIZE.html
Checks 100% word-for-word text preservation, heading counts, absence of Word artifacts, and footnote anchors.
"""

import re
import subprocess

def test_verification():
    # 1. Read current cleaned file
    with open('QUATREVINGT-TREIZE.html', 'r', encoding='utf-8') as f:
        clean_html = f.read()

    # 2. Get original raw text from git HEAD
    orig_html = subprocess.check_output(['git', 'show', 'HEAD:QUATREVINGT-TREIZE.html']).decode('utf-8', errors='ignore')

    # Verify headings preservation counts
    orig_h1 = re.findall(r'<h1[^>]*>(.*?)</h1>', orig_html, re.S)
    clean_h1 = re.findall(r'<h1(?:\s+[^>]*)?>(.*?)</h1>', clean_html, re.S)
    print(f"H1 count: orig={len(orig_h1)}, clean={len(clean_h1)}")
    assert len(orig_h1) == 3, f"Expected 3 novel h1s, got {len(orig_h1)}"
    assert len(clean_h1) == 4, f"Expected 4 h1s (including title page), got {len(clean_h1)}"

    orig_h2 = re.findall(r'<h2[^>]*>(.*?)</h2>', orig_html, re.S)
    clean_h2 = re.findall(r'<h2(?:\s+[^>]*)?>(.*?)</h2>', clean_html, re.S)
    print(f"H2 count: orig={len(orig_h2)}, clean={len(clean_h2)}")
    assert len(orig_h2) == 14, f"Expected 14 novel h2s, got {len(orig_h2)}"
    assert len(clean_h2) == 15, f"Expected 15 h2s (including notes), got {len(clean_h2)}"

    orig_h3 = re.findall(r'<h3[^>]*>(.*?)</h3>', orig_html, re.S)
    clean_h3 = re.findall(r'<h3(?:\s+[^>]*)?>(.*?)</h3>', clean_html, re.S)
    print(f"H3 count: orig={len(orig_h3)}, clean={len(clean_h3)}")
    assert len(orig_h3) == 82, f"Expected 82 h3s, got {len(orig_h3)}"
    assert len(clean_h3) == 82, f"Expected 82 clean h3s, got {len(clean_h3)}"

    orig_h4 = re.findall(r'<h4[^>]*>(.*?)</h4>', orig_html, re.S)
    clean_h4 = re.findall(r'<h4(?:\s+[^>]*)?>(.*?)</h4>', clean_html, re.S)
    print(f"H4 count: orig={len(orig_h4)}, clean={len(clean_h4)}")
    assert len(orig_h4) == 19, f"Expected 19 h4s, got {len(orig_h4)}"
    assert len(clean_h4) == 19, f"Expected 19 clean h4s, got {len(clean_h4)}"

    # Check word-for-word preservation of the novel text
    h1_orig = orig_html.find('<h1>')
    fn_orig = orig_html.find('<div id="ftn1">')
    orig_novel = orig_html[h1_orig:fn_orig]

    h1_clean = clean_html.find('<main>')
    fn_clean = clean_html.find('</main>')
    clean_novel = clean_html[h1_clean:fn_clean]

    def get_words(text):
        t = re.sub(r'<[^>]+>', ' ', text)
        t = re.sub(r'\[[1-4]\]', ' ', t)
        t = t.replace('&nbsp;', ' ')
        return re.findall(r'[\w’\'-]+', t)

    orig_words = get_words(orig_novel)
    clean_words = get_words(clean_novel)
    assert orig_words == clean_words, f"Word match failed! {len(orig_words)} vs {len(clean_words)}"
    print(f"Preserved exactly {len(orig_words)} words (100% match).")

    # Verify no Word Mso artifacts remain
    assert 'Mso' not in clean_html, "Found Mso artifacts in clean HTML"
    assert '@font-face' not in clean_html, "Found @font-face in clean HTML"
    assert '<span' not in clean_html, "Found <span> tags in clean HTML"
    assert 'ebooksgratuits' not in clean_html, "Found ebooksgratuits link in clean HTML"
    assert 'hugo.jpg' not in clean_html, "Found hugo.jpg reference in clean HTML"

    # Verify footnotes integrity
    assert '<section class="footnotes-section">' in clean_html
    for i in range(1, 5):
        assert f'href="#ftn{i}" id="ftnref{i}"' in clean_html, f"Footnote ref {i} missing"
        assert f'id="ftn{i}" class="footnote-text"' in clean_html, f"Footnote text {i} missing"
        assert f'href="#ftnref{i}" class="footnote-back"' in clean_html, f"Footnote backlink {i} missing"

    # Verify KDP @page CSS
    assert 'size: 6in 9in;' in clean_html
    assert 'hyphens: auto;' in clean_html
    assert 'margin-inside: 22mm;' in clean_html

    print("ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == '__main__':
    test_verification()
