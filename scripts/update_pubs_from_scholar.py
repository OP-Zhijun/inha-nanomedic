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
        title_raw, journal_raw, year_raw, link = mt.groups()
        title = html_mod.unescape(re.sub(r"<[^>]+>", "", title_raw)).strip()
        journal = html_mod.unescape(re.sub(r"<[^>]+>", "", journal_raw)).strip()
        rows.append({
            "raw": mt.group(0),
            "title": title,
            "journal": journal,
            "year": _year_to_int(year_raw),
            "norm": normalize(title),
        })
    return rows


ROW_INDENT = "          "  # 10 spaces, matches publication-patent.html


def resort_tbody(html_content, new_row_strings):
    """Rebuild the <tbody> with existing + new rows, sorted year-descending.

    Existing rows are re-emitted from their preserved raw HTML (unchanged).
    Sort is stable: within the same year, existing rows keep their prior order
    and new rows follow them. Only ordering changes — no row is edited/dropped.
    """
    existing = parse_existing_rows(html_content)
    combined = [{"year": r["year"], "raw": r["raw"]} for r in existing]
    for s in new_row_strings:
        mt = ROW_RE.search(s)
        yr = _year_to_int(mt.group(3)) if mt else 0
        combined.append({"year": yr, "raw": s.strip()})

    combined.sort(key=lambda r: -r["year"])  # stable; preserves same-year order

    body = "\n".join(ROW_INDENT + r["raw"] for r in combined)
    new_tbody = "<tbody>\n" + body + "\n" + ROW_INDENT[:-2] + "</tbody>"

    start = html_content.find("<tbody>")
    end = html_content.find("</tbody>") + len("</tbody>")
    if start == -1 or end == -1:
        raise ValueError("tbody not found in HTML")
    return html_content[:start] + new_tbody + html_content[end:]
