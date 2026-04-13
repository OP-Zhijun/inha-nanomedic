"""
INHA NANOMEDIC Site QA Checker
Runs automatically after any edit to verify site consistency.
"""
import re, os, sys, glob

sys.stdout.reconfigure(encoding='utf-8')
site_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html_files = sorted(glob.glob(os.path.join(site_dir, '*.html')))

errors = []
warnings = []

def check(label, condition, detail=''):
    if not condition:
        errors.append(f'FAIL: {label}' + (f' — {detail}' if detail else ''))

def warn(label, detail=''):
    warnings.append(f'WARN: {label}' + (f' — {detail}' if detail else ''))

# Read all HTML files
pages = {}
for f in html_files:
    with open(f, 'r', encoding='utf-8') as fh:
        pages[os.path.basename(f)] = fh.read()

print(f'Checking {len(pages)} pages...\n')

# ══════════════════════════════════════════
# 1. FAVICON on all pages
# ══════════════════════════════════════════
for name, html in pages.items():
    check(f'{name}: favicon', 'favicon' in html, 'Missing <link rel="icon">')

# ══════════════════════════════════════════
# 2. META DESCRIPTION on all pages
# ══════════════════════════════════════════
for name, html in pages.items():
    check(f'{name}: meta description', 'meta name="description"' in html, 'Missing <meta name="description">')

# ══════════════════════════════════════════
# 3. TITLE TAG consistency
# ══════════════════════════════════════════
title_pattern = re.compile(r'<title>(.*?)</title>')
titles = {}
for name, html in pages.items():
    m = title_pattern.search(html)
    titles[name] = m.group(1) if m else ''

# All inner pages should end with "INHA NANOMEDIC"
for name, title in titles.items():
    if name != 'index.html':
        check(f'{name}: title format', 'INHA NANOMEDIC' in title, f'Title: "{title}" — should contain "INHA NANOMEDIC"')

# ══════════════════════════════════════════
# 4. FOOTER consistency
# ══════════════════════════════════════════
footer_pattern = re.compile(r'Designed by Zhijun ZHAO')
copyright_pattern = re.compile(r'&copy; (\d{4})')

for name, html in pages.items():
    check(f'{name}: footer credit', footer_pattern.search(html), 'Missing "Designed by Zhijun ZHAO"')
    m = copyright_pattern.search(html)
    if m:
        check(f'{name}: copyright year', m.group(1) == '2026', f'Copyright year is {m.group(1)}, should be 2026')

# ══════════════════════════════════════════
# 5. EMAIL consistency
# ══════════════════════════════════════════
emails_found = {}
email_pattern = re.compile(r'mailto:([^"]+)')
for name, html in pages.items():
    found = email_pattern.findall(html)
    if found:
        emails_found[name] = set(found)

# Check no page uses diavex@naver.com
for name, emails in emails_found.items():
    for e in emails:
        if 'naver' in e.lower():
            errors.append(f'FAIL: {name}: uses personal email {e} — should use sugeun.yang@inha.ac.kr')

# ══════════════════════════════════════════
# 6. NAVIGATION consistency
# ══════════════════════════════════════════
nav_links = ['about.html', 'research.html', 'member.html', 'publication-patent.html',
             'lab-facilities.html', 'lab-activities.html', 'benefit.html', 'news-notice.html']

for name, html in pages.items():
    for link in nav_links:
        check(f'{name}: nav link to {link}', link in html, f'Missing nav link to {link}')

# Check no links to alumni.html
for name, html in pages.items():
    if 'alumni.html' in html:
        errors.append(f'FAIL: {name}: links to deleted alumni.html')

# ══════════════════════════════════════════
# 7. PLACEHOLDER links (href="#")
# ══════════════════════════════════════════
for name, html in pages.items():
    href_hash = len(re.findall(r'href="#"', html))
    if href_hash > 0:
        errors.append(f'FAIL: {name}: {href_hash} placeholder href="#" links found')

# ══════════════════════════════════════════
# 8. PUBLICATION count vs stats bar
# ══════════════════════════════════════════
if 'publication-patent.html' in pages:
    pub_rows = len(re.findall(r'<tr><td>', pages['publication-patent.html']))

if 'index.html' in pages:
    # Find the stat-item that contains "Publications"
    pub_stat_match = re.search(r'data-count="(\d+)"[^<]*</div>\s*<div class="stat-label">Publications', pages['index.html'], re.DOTALL)
    if pub_stat_match:
        stat_count = int(pub_stat_match.group(1))
        if abs(pub_rows - stat_count) > 2:
            errors.append(f'FAIL: Stats bar says {stat_count} publications but table has {pub_rows} rows')

# ══════════════════════════════════════════
# 9. RESEARCH AREAS count vs stats bar
# ══════════════════════════════════════════
if 'research.html' in pages:
    research_cards = len(re.findall(r'class="research-card', pages['research.html']))

if 'index.html' in pages:
    research_stat = re.search(r'data-count="(\d+)"[^<]*</div>\s*<div class="stat-label">Research Areas', pages['index.html'], re.DOTALL)
    if research_stat:
        research_count = int(research_stat.group(1))
        check('Stats vs research cards', research_count == research_cards,
              f'Stats says {research_count} but research.html has {research_cards} cards')

# ══════════════════════════════════════════
# 10. PILLAR consistency (index vs about)
# ══════════════════════════════════════════
pillar_pattern = re.compile(r'class="pillar-title">(.*?)</div>')
for page_name in ['index.html', 'about.html']:
    if page_name in pages:
        pillars = pillar_pattern.findall(pages[page_name])
        if pillars:
            # Check pillars match between pages
            pass  # Will compare below

if 'index.html' in pages and 'about.html' in pages:
    index_pillars = set(pillar_pattern.findall(pages['index.html']))
    about_pillars = set(pillar_pattern.findall(pages['about.html']))
    if index_pillars and about_pillars and index_pillars != about_pillars:
        errors.append(f'FAIL: Pillar mismatch — index.html has {index_pillars} but about.html has {about_pillars}')

# ══════════════════════════════════════════
# 11. STALE TEXT checks
# ══════════════════════════════════════════
stale_patterns = [
    ('six core research', 'Should be "three"'),
    ('six interconnected', 'Should be "three"'),
    ('Nuclear Medicine', 'Wrong department name'),
    ('Chungbuk University', 'Should be Chungang University'),
]
for pattern, reason in stale_patterns:
    for name, html in pages.items():
        if pattern.lower() in html.lower():
            errors.append(f'FAIL: {name}: contains stale text "{pattern}" — {reason}')

# ══════════════════════════════════════════
# 12. SECURITY: rel="noopener noreferrer"
# ══════════════════════════════════════════
for name, html in pages.items():
    blank_links = len(re.findall(r'target="_blank"', html))
    safe_links = len(re.findall(r'target="_blank"\s+rel="noopener noreferrer"', html))
    if blank_links > safe_links:
        errors.append(f'FAIL: {name}: {blank_links - safe_links} target="_blank" links missing rel="noopener noreferrer"')

# ══════════════════════════════════════════
# 13. IMAGES exist
# ══════════════════════════════════════════
img_pattern = re.compile(r'src="(assets/[^"]+)"')
for name, html in pages.items():
    for img_path in img_pattern.findall(html):
        clean_path = img_path.split('?')[0]  # strip query params (?v=2 etc.)
        full_path = os.path.join(site_dir, clean_path)
        if not os.path.exists(full_path):
            errors.append(f'FAIL: {name}: broken image — {img_path} does not exist')

# ══════════════════════════════════════════
# REPORT
# ══════════════════════════════════════════
print('=' * 60)
if errors:
    print(f'FAILED — {len(errors)} issues found:\n')
    for e in errors:
        print(f'  {e}')
else:
    print('ALL CHECKS PASSED')

if warnings:
    print(f'\n{len(warnings)} warnings:')
    for w in warnings:
        print(f'  {w}')

print(f'\n{len(pages)} pages checked, {len(errors)} errors, {len(warnings)} warnings')
print('=' * 60)

sys.exit(1 if errors else 0)
