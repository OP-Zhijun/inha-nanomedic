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
        if mt is None:
            raise ValueError(f"new row string does not match expected <tr> format: {s!r}")
        yr = _year_to_int(mt.group(3))
        combined.append({"year": yr, "raw": s.strip()})

    combined.sort(key=lambda r: -r["year"])  # stable; preserves same-year order

    body = "\n".join(ROW_INDENT + r["raw"] for r in combined)
    new_tbody = "<tbody>\n" + body + "\n" + ROW_INDENT[:-2] + "</tbody>"

    start = html_content.find("<tbody>")
    end_raw = html_content.find("</tbody>")
    if start == -1 or end_raw == -1:
        raise ValueError("tbody not found in HTML")
    end = end_raw + len("</tbody>")
    return html_content[:start] + new_tbody + html_content[end:]


SIMILARITY_THRESHOLD = 0.90


def crossref_best_match(title, items):
    """Pick the best Crossref item for `title`. Return {doi, journal, year} or None.

    Accept only if the best candidate is a journal-article AND its normalized
    title is >= SIMILARITY_THRESHOLD similar. This is the junk filter: abstracts,
    proceedings, and unrelated hits are rejected (returns None).
    """
    want = normalize(title)
    best, best_score = None, 0.0
    for it in items:
        cand_titles = it.get("title") or []
        if not cand_titles:
            continue
        score = SequenceMatcher(None, want, normalize(cand_titles[0])).ratio()
        if score > best_score:
            best, best_score = it, score
    if best is None or best_score < SIMILARITY_THRESHOLD:
        return None
    if best.get("type") != "journal-article":
        return None
    journal_list = best.get("container-title") or [""]
    parts = best.get("issued", {}).get("date-parts", [[None]])
    year = parts[0][0] if parts and parts[0] else None
    return {
        "doi": best.get("DOI", "").strip(),
        "journal": journal_list[0].strip(),
        "year": str(year) if year else "",
    }


def update_counters(pub_html, index_html, total_count):
    """Return (pub_html, index_html) with both publication counters set to total_count.

    Updates: (1) the meta description "<N> peer-reviewed publications" on the
    publications page, and (2) the stats-bar data-count above "Publications" on
    the homepage. qa_check.py independently verifies these match the row count.
    """
    pub_html = re.sub(
        r'content="\d+ peer-reviewed publications',
        f'content="{total_count} peer-reviewed publications',
        pub_html,
    )
    lines = index_html.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if 'data-count="' in line and i + 1 < len(lines) and "Publications" in lines[i + 1]:
            old = re.search(r'data-count="(\d+)"', line)
            if old:
                lines[i] = line.replace(
                    f'data-count="{old.group(1)}"', f'data-count="{total_count}"'
                )
                break
    return pub_html, "".join(lines)
