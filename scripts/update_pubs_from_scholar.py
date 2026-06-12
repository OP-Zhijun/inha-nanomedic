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


# ── Network wrappers (thin I/O over the pure logic above; exercised live, ──
# ── not unit-tested). The module requires `requests` to import.          ──
import requests  # noqa: E402

SERPAPI_URL = "https://serpapi.com/search"
CROSSREF_URL = "https://api.crossref.org/works"
POLITE_MAILTO = "inha.nanomedic@gmail.com"  # Crossref polite pool contact


def fetch_scholar_articles(api_key):
    """Return [{title, year, venue}, ...] for the whole Scholar profile.

    Paginates the SerpApi google_scholar_author engine until all articles are read.
    """
    articles, start = [], 0
    while True:
        params = {
            "engine": "google_scholar_author",
            "author_id": SCHOLAR_AUTHOR_ID,
            "api_key": api_key,
            "num": 100,
            "start": start,
            "sort": "pubdate",
        }
        resp = requests.get(SERPAPI_URL, params=params, timeout=60)
        resp.raise_for_status()
        batch = resp.json().get("articles", [])
        if not batch:
            break
        for a in batch:
            articles.append({
                "title": (a.get("title") or "").strip(),
                "year": str(a.get("year") or "").strip(),
                "venue": (a.get("publication") or "").strip(),
            })
        if len(batch) < 100:
            break
        start += 100
    return articles


def crossref_lookup(title):
    """Query Crossref by title; return {doi, journal, year} or None (uses the filter)."""
    params = {"query.bibliographic": title, "rows": 5, "mailto": POLITE_MAILTO}
    try:
        resp = requests.get(CROSSREF_URL, params=params, timeout=60)
        resp.raise_for_status()
        items = resp.json().get("message", {}).get("items", [])
    except requests.RequestException:
        return None
    return crossref_best_match(title, items)


# ── Orchestration / CLI ──
import os       # noqa: E402
import sys      # noqa: E402
import argparse # noqa: E402
import shutil   # noqa: E402

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "publication-patent.html"))
INDEX_FILE = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "index.html"))
PREVIEW_FILE = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "publication-patent.preview.html"))


def build_new_rows(papers):
    """Build single-line <tr> strings for verified new papers (DOI link)."""
    rows = []
    for p in papers:
        t = html_mod.escape(p["title"])
        j = html_mod.escape(p["journal"])
        y = html_mod.escape(p["year"])
        url = f"https://doi.org/{html_mod.escape(p['doi'])}"
        link = (f'<a href="{url}" target="_blank" '
                f'rel="noopener noreferrer" class="btn-outline btn-small">DOI</a>')
        rows.append(f"<tr><td>{t}</td><td>{j}</td><td>{y}</td><td>{link}</td></tr>")
    return rows


def write_report(path, added, filtered):
    lines = []
    if added:
        lines.append(f"### {len(added)} new publication(s) added\n")
        for p in added:
            lines.append(f"- **[{p['year']}]** {p['title']}  \n  "
                         f"_{p['journal']}_ — https://doi.org/{p['doi']}")
    else:
        lines.append("### No new publications this run\n")
    if filtered:
        lines.append(f"\n### {len(filtered)} entr(y/ies) filtered out (NOT published — review)\n")
        for f in filtered:
            lines.append(f"- {f['title']}  _(reason: {f['reason']})_")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true",
                   help="write to publication-patent.preview.html, never the live file")
    g.add_argument("--apply", action="store_true",
                   help="write the live publication-patent.html and index.html (PR branch only)")
    ap.add_argument("--report", default=os.path.join(SCRIPT_DIR, "..", "scholar_update_report.md"))
    args = ap.parse_args()
    if not args.dry_run and not args.apply:
        args.dry_run = True  # safe default

    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        print("ERROR: SERPAPI_KEY environment variable not set.")
        sys.exit(2)

    with open(HTML_FILE, encoding="utf-8") as f:
        pub_html = f.read()
    existing = parse_existing_rows(pub_html)
    existing_norms = {r["norm"] for r in existing}
    print(f"{len(existing)} papers already on the site.")

    scholar = fetch_scholar_articles(api_key)
    print(f"{len(scholar)} entries on Google Scholar.")

    new_candidates, seen = [], set()
    for s in scholar:
        n = normalize(s["title"])
        if not n or n in existing_norms or n in seen:
            continue
        seen.add(n)
        new_candidates.append(s)
    print(f"{len(new_candidates)} candidate new title(s) after diff.")

    added, filtered = [], []
    for s in new_candidates:
        match = crossref_lookup(s["title"])
        if match and match["doi"]:
            added.append({
                "title": s["title"],
                "journal": match["journal"] or s["venue"],
                "year": match["year"] or s["year"],
                "doi": match["doi"],
            })
        else:
            reason = "no-crossref-journal-match"
            filtered.append({"title": s["title"], "reason": reason})

    # House rule: show the first <=5 detected papers for verification.
    print("\nFirst detected new papers (verify before publishing):")
    for i, p in enumerate(added[:5], 1):
        print(f"  {i}. [{p['year']}] {p['title'][:75]}  (DOI {p['doi']})")
    if filtered:
        print(f"\n{len(filtered)} filtered (not published):")
        for f in filtered[:5]:
            print(f"  - {f['title'][:75]}  ({f['reason']})")

    write_report(args.report, added, filtered)

    if not added:
        print("\nNothing verified to add. Site untouched.")
        return

    new_rows = build_new_rows(added)
    total = len(existing) + len(added)
    new_pub_html = resort_tbody(pub_html, new_rows)
    with open(INDEX_FILE, encoding="utf-8") as f:
        index_html = f.read()
    new_pub_html, new_index_html = update_counters(new_pub_html, index_html, total)

    if args.dry_run:
        shutil.copy2(HTML_FILE, PREVIEW_FILE + ".orig")  # keep a reference copy
        with open(PREVIEW_FILE, "w", encoding="utf-8") as f:
            f.write(new_pub_html)
        print(f"\nDRY RUN: wrote preview to {PREVIEW_FILE} (live file untouched). "
              f"Total would be {total}.")
    else:
        with open(HTML_FILE, "w", encoding="utf-8") as f:
            f.write(new_pub_html)
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            f.write(new_index_html)
        print(f"\nAPPLIED: added {len(added)} paper(s). Total now {total}.")


if __name__ == "__main__":
    main()
