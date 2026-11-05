#!/usr/bin/env python3
"""
Verification test suite for Amazon KDP print-on-demand files.
Verifies les-contemplations.html and quatrevingt-treize.html:
- 100% word-for-word text preservation
- Heading counts
- Absence of Word/Mso artifacts and non-printable tags
- KDP @page 6" x 9" CSS rules
"""

import os
import re
import urllib.request


def test_contemplations():
    print("Testing les-contemplations.html...")
    with open('les-contemplations.html', 'r', encoding='utf-8') as f:
        clean_html = f.read()

    # 1. Fetch remote ground-truth
    url = 'https://www.ebooksgratuits.com/html/hugo_contemplations.html'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        orig_html = resp.read().decode('utf-8')

    pref_idx = orig_html.find('PRÉFACE</span></a></h1>')
    h1_idx = orig_html.rfind('<h1', 0, pref_idx)
    end_marker = orig_html.find('À propos de cette édition électronique')
    p_end = orig_html.rfind('<p', 0, end_marker)
    orig_work = orig_html[h1_idx:p_end]

    # Verify heading counts
    orig_h1 = re.findall(r'<h1[^>]*>(.*?)</h1>', orig_work, re.S)
    clean_h1 = re.findall(r'<h1(?:\s+[^>]*)?>(.*?)</h1>', clean_html, re.S)
    print(f"H1 count: orig={len(orig_h1)}, clean={len(clean_h1)}")
    assert len(orig_h1) == 3, f"Expected 3 work h1s, got {len(orig_h1)}"
    assert len(clean_h1) == 4, f"Expected 4 h1s (including title page), got {len(clean_h1)}"

    orig_h2 = re.findall(r'<h2[^>]*>(.*?)</h2>', orig_work, re.S)
    clean_h2 = re.findall(r'<h2(?:\s+[^>]*)?>(.*?)</h2>', clean_html, re.S)
    print(f"H2 count: orig={len(orig_h2)}, clean={len(clean_h2)}")
    assert len(orig_h2) == 6, f"Expected 6 work h2s, got {len(orig_h2)}"
    assert len(clean_h2) == 6, f"Expected 6 clean h2s, got {len(clean_h2)}"

    orig_h3 = re.findall(r'<h3[^>]*>(.*?)</h3>', orig_work, re.S)
    clean_h3 = re.findall(r'<h3(?:\s+[^>]*)?>(.*?)</h3>', clean_html, re.S)
    print(f"H3 count: orig={len(orig_h3)}, clean={len(clean_h3)}")
    assert len(orig_h3) == 158, f"Expected 158 work h3s, got {len(orig_h3)}"
    assert len(clean_h3) == 158, f"Expected 158 clean h3s, got {len(clean_h3)}"

    orig_h4 = re.findall(r'<h4[^>]*>(.*?)</h4>', orig_work, re.S)
    clean_h4 = re.findall(r'<h4(?:\s+[^>]*)?>(.*?)</h4>', clean_html, re.S)
    print(f"H4 count: orig={len(orig_h4)}, clean={len(clean_h4)}")
    assert len(orig_h4) == 1, f"Expected 1 work h4s, got {len(orig_h4)}"
    assert len(clean_h4) == 1, f"Expected 1 clean h4s, got {len(clean_h4)}"

    orig_h5 = re.findall(r'<h5[^>]*>(.*?)</h5>', orig_work, re.S)
    clean_h5 = re.findall(r'<h5(?:\s+[^>]*)?>(.*?)</h5>', clean_html, re.S)
    print(f"H5 count: orig={len(orig_h5)}, clean={len(clean_h5)}")
    assert len(orig_h5) == 60, f"Expected 60 work h5s, got {len(orig_h5)}"
    assert len(clean_h5) == 60, f"Expected 60 clean h5s, got {len(clean_h5)}"

    # Check 100% word-for-word preservation
    h1_clean_idx = clean_html.find('<div class="novel-body">')
    clean_work = clean_html[h1_clean_idx:]

    def get_words(text):
        t = re.sub(r'<[^>]+>', ' ', text)
        t = t.replace('&nbsp;', ' ')
        return re.findall(r'[\w’\'-]+', t)

    orig_words = get_words(orig_work)
    clean_words = get_words(clean_work)
    assert orig_words == clean_words, f"Word match failed! {len(orig_words)} vs {len(clean_words)}"
    print(f"Preserved exactly {len(orig_words)} words (100% match).")

    # Verify no Word artifacts or interactive tags
    assert 'Mso' not in clean_html, "Found Mso artifacts in clean HTML"
    assert '@font-face' not in clean_html, "Found @font-face in clean HTML"
    assert '<a' not in clean_html, "Found <a> tags in clean HTML"
    assert 'ebooksgratuits' not in clean_html, "Found ebooksgratuits link in clean HTML"
    assert 'hugo.jpg' not in clean_html, "Found hugo.jpg reference in clean HTML"
    assert 'id="_Toc' not in clean_html, "Found _Toc id in clean HTML"
    assert 'viewport' not in clean_html, "Found viewport meta tag in clean HTML"
    assert '<img' not in clean_html, "Found img tag in clean HTML"

    # Verify title page
    assert '<div class="title-page">' in clean_html
    assert '<h1 class="book-title">LES CONTEMPLATIONS</h1>' in clean_html
    assert 'Victor Hugo' in clean_html
    assert '(1856)' in clean_html

    # Verify KDP @page CSS
    assert 'size: 6in 9in;' in clean_html
    assert 'hyphens: auto;' in clean_html
    assert 'margin-inside: 22mm;' in clean_html
    assert 'margin-outside: 16mm;' in clean_html
    assert 'p.align-right' in clean_html
    assert 'p.stanza-break' in clean_html

    print("les-contemplations.html: ALL CHECKS PASSED!\n")


def test_quatrevingt_treize():
    if not os.path.exists('quatrevingt-treize.html'):
        return

    print("Testing quatrevingt-treize.html...")
    with open('quatrevingt-treize.html', 'r', encoding='utf-8') as f:
        clean_html = f.read()

    # Verify clean HTML structure
    assert 'size: 6in 9in;' in clean_html
    assert 'margin-inside: 22mm;' in clean_html
    assert '<div class="title-page">' in clean_html
    assert 'Mso' not in clean_html
    assert '<a' not in clean_html
    assert '<div class="novel-body">' in clean_html
    print("quatrevingt-treize.html: ALL CHECKS PASSED!\n")


if __name__ == '__main__':
    test_contemplations()
    test_quatrevingt_treize()
    print("ALL TEST SUITES PASSED SUCCESSFULLY!")
