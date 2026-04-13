#!/usr/bin/env python3
"""
Merge new publications from Zotero into publication-patent.html.

Source:  ~/Zotero/zotero.sqlite
         Collection: Nano_Lab_published_papers (ID 54)

Usage:   cd C:\\Users\\karol\\nanomedic
         python scripts/update_pubs_from_zotero.py

What it does:
  1. Copies the Zotero DB to a temp file (avoids lock conflicts)
  2. Reads all items from the target collection
  3. Compares against existing papers already in the HTML table
  4. Adds ONLY genuinely new papers (matched by normalized title)
  5. New papers link to https://doi.org/<DOI> — no PDF upload needed
  6. Existing papers (with their PDF links) are preserved untouched

Re-run any time new papers are added to the Zotero collection.
"""

import sqlite3
import shutil
import os
import re
import sys
import io
import html as html_mod
import tempfile

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Config ──
ZOTERO_DB   = os.path.expanduser(r"~\Zotero\zotero.sqlite")
COLLECTION  = 54  # Nano_Lab_published_papers
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
HTML_FILE   = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "publication-patent.html"))
INDEX_FILE  = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "index.html"))


def normalize(text):
    """Lowercase, strip HTML tags and non-alphanumeric chars for comparison."""
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"[^a-z0-9]", "", text.lower())


def copy_db():
    tmp = os.path.join(tempfile.gettempdir(), "zotero_copy.sqlite")
    shutil.copy2(ZOTERO_DB, tmp)
    return tmp


def fetch_zotero_papers(db_path):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    c = conn.cursor()

    c.execute("SELECT itemID FROM collectionItems WHERE collectionID = ?", (COLLECTION,))
    item_ids = [r[0] for r in c.fetchall()]

    papers = []
    seen_dois = set()

    for iid in item_ids:
        c.execute("""
            SELECT f.fieldName, idv.value
            FROM itemData id
            JOIN fields f ON id.fieldID = f.fieldID
            JOIN itemDataValues idv ON id.valueID = idv.valueID
            WHERE id.itemID = ?
        """, (iid,))
        fields = dict(c.fetchall())

        title   = re.sub(r"<[^>]+>", "", fields.get("title", "")).strip()
        journal = fields.get("publicationTitle",
                             fields.get("journalAbbreviation", "")).strip()
        date    = fields.get("date", "")
        doi     = fields.get("DOI", "").strip()
        year    = date[:4] if date else ""

        if not title:
            continue
        if doi:
            if doi in seen_dois:
                continue
            seen_dois.add(doi)

        papers.append({
            "title": title, "journal": journal,
            "year": year, "doi": doi,
            "norm": normalize(title),
        })

    conn.close()
    papers.sort(key=lambda p: (-int(p["year"] or "0"), p["title"]))
    return papers


def get_existing_norms(html_content):
    """Extract normalized titles already in the HTML table."""
    norms = set()
    for m in re.finditer(r"<tr><td>(.*?)</td><td>", html_content):
        raw = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        norms.add(normalize(raw))
    return norms


def build_new_rows(papers):
    rows = []
    for p in papers:
        t = html_mod.escape(p["title"])
        j = html_mod.escape(p["journal"])
        y = html_mod.escape(p["year"])
        if p["doi"]:
            url = f"https://doi.org/{html_mod.escape(p['doi'])}"
            link = (f'<a href="{url}" target="_blank" '
                    f'rel="noopener noreferrer" class="btn-outline btn-small">DOI</a>')
        else:
            link = '<span style="color:var(--muted); font-size:0.72rem;">&mdash;</span>'
        rows.append(f"          <tr><td>{t}</td><td>{j}</td><td>{y}</td><td>{link}</td></tr>")
    return rows


def update_html(new_rows, total_count):
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # Insert new rows right after <tbody>
    insert_point = content.find("<tbody>") + len("<tbody>") + 1  # +1 for newline
    if insert_point <= len("<tbody>"):
        print("ERROR: <tbody> not found in", HTML_FILE)
        return False

    new_block = "\n".join(new_rows) + "\n"
    content = content[:insert_point] + new_block + content[insert_point:]

    # Update meta description count
    content = re.sub(
        r'content="\d+ peer-reviewed publications',
        f'content="{total_count} peer-reviewed publications',
        content
    )

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    # Also update homepage stats bar counter (line-by-line to avoid regex corruption)
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            if 'data-count="' in line and i + 1 < len(lines) and "Publications" in lines[i + 1]:
                old = re.search(r'data-count="(\d+)"', line)
                if old:
                    lines[i] = line.replace(f'data-count="{old.group(1)}"', f'data-count="{total_count}"')
                    break
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"  Homepage stats bar updated to {total_count}")

    return True


def main():
    print(f"Copying Zotero DB ...")
    tmp_db = copy_db()

    print(f"Reading collection {COLLECTION} ...")
    zotero_papers = fetch_zotero_papers(tmp_db)
    print(f"  {len(zotero_papers)} unique papers in Zotero")

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html_content = f.read()

    existing = get_existing_norms(html_content)
    existing_count = len(existing)
    print(f"  {existing_count} papers already on the site")

    # Filter to genuinely new papers only
    new_papers = [p for p in zotero_papers if p["norm"] not in existing]
    print(f"  {len(new_papers)} NEW papers to add")

    if not new_papers:
        print("\nNothing to add — the site is already up to date.")
        os.remove(tmp_db)
        return

    print("\nNew papers:")
    for i, p in enumerate(new_papers, 1):
        print(f"  {i}. [{p['year']}] {p['title'][:75]}")
        print(f"     DOI: {p['doi']}")

    new_rows = build_new_rows(new_papers)
    total = existing_count + len(new_papers)

    print(f"\nUpdating {HTML_FILE} ...")
    if update_html(new_rows, total):
        print(f"Done. Added {len(new_papers)} papers. Total now: {total}.")
    else:
        print("FAILED.")

    os.remove(tmp_db)


if __name__ == "__main__":
    main()
