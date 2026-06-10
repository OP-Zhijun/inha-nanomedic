#!/usr/bin/env python3
"""
Merge new publications from Google Scholar into publication-patent.html.

Source:  Google Scholar profile X1B7JX8AAAAJ (Prof. Sugeun Yang), via SerpApi.
Enrich:  Crossref (title -> DOI + journal + year). This is ALSO the junk filter:
         an entry with no confident journal-article match is NOT published.

The live site only changes when a human merges the PR this produces.
See docs/superpowers/specs/2026-06-10-publication-auto-update-design.md
"""
import re
import html as html_mod
from difflib import SequenceMatcher

SCHOLAR_AUTHOR_ID = "X1B7JX8AAAAJ"

ROW_RE = re.compile(
    r"<tr><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td></tr>",
    re.DOTALL,
)


def normalize(text):
    """Lowercase, strip HTML tags and non-alphanumeric chars for comparison."""
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _year_to_int(text):
    m = re.search(r"\d{4}", text or "")
    return int(m.group(0)) if m else 0


def parse_existing_rows(html_content):
    """Return list of dicts for every <tr> in the tbody, preserving the raw row.

    Each dict: {raw, title, journal, year(int), norm}. Raw is the exact
    original '<tr>...</tr>' string so existing rows can be re-emitted unchanged.
    """
    start = html_content.find("<tbody>")
    end = html_content.find("</tbody>")
    region = html_content[start:end] if start != -1 and end != -1 else html_content
    rows = []
    for mt in ROW_RE.finditer(region):
        title_raw, journal, year_raw, link = mt.groups()
        title = re.sub(r"<[^>]+>", "", title_raw).strip()
        rows.append({
            "raw": mt.group(0),
            "title": title,
            "journal": journal,
            "year": _year_to_int(year_raw),
            "norm": normalize(title),
        })
    return rows
