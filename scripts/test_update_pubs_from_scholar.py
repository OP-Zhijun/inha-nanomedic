import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update_pubs_from_scholar as m

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "sample_table.html")

def load_fixture():
    with open(FIX, encoding="utf-8") as f:
        return f.read()

# tests are added in later tasks

def test_normalize_strips_tags_and_punct():
    assert m.normalize("Nano-<i>Particles</i>, for Cancer!") == "nanoparticlesforcancer"

def test_parse_existing_rows_extracts_title_year_raw():
    rows = m.parse_existing_rows(load_fixture())
    assert len(rows) == 2
    titles = [r["title"] for r in rows]
    assert "Older Paper About Liposomes" in titles
    assert "Newer Paper About Hydrogels" in titles
    by_title = {r["title"]: r for r in rows}
    assert by_title["Newer Paper About Hydrogels"]["year"] == 2023
    # raw must be the exact original <tr>...</tr>
    assert by_title["Older Paper About Liposomes"]["raw"].startswith("<tr><td>Older Paper")
    assert by_title["Older Paper About Liposomes"]["raw"].endswith("</tr>")

def test_parse_unescapes_html_entities_for_dedup():
    html = ('<tbody>\n'
            '          <tr><td>Cancer Research &amp; Treatment</td>'
            '<td>Materials &amp; Interfaces</td><td>2020</td>'
            '<td><a href="x">DOI</a></td></tr>\n'
            '        </tbody>')
    rows = m.parse_existing_rows(html)
    assert rows[0]["title"] == "Cancer Research & Treatment"
    assert rows[0]["journal"] == "Materials & Interfaces"
    # de-dup parity: the normalized stored title must equal the normalized
    # plain-text Scholar title (no stray "amp" from a leftover &amp;)
    assert rows[0]["norm"] == m.normalize("Cancer Research & Treatment")
    assert "amp" not in rows[0]["norm"]

def test_resort_orders_year_descending():
    html = load_fixture()
    out = m.resort_tbody(html, [])  # no new rows
    rows = m.parse_existing_rows(out)
    years = [r["year"] for r in rows]
    assert years == sorted(years, reverse=True)   # 2023 before 2019

def test_resort_zero_new_loses_no_rows():
    """Safety invariant: with no new rows, the SAME set of <tr> survives."""
    html = load_fixture()
    before = {r["raw"] for r in m.parse_existing_rows(html)}
    out = m.resort_tbody(html, [])
    after = {r["raw"] for r in m.parse_existing_rows(out)}
    assert before == after          # nothing dropped, nothing altered

def test_resort_inserts_new_row_in_year_order():
    html = load_fixture()
    new = ["<tr><td>Mid Paper</td><td>ACS Nano</td><td>2021</td><td><a href=\"d\">DOI</a></td></tr>"]
    out = m.resort_tbody(html, new)
    rows = m.parse_existing_rows(out)
    years = [r["year"] for r in rows]
    assert years == [2023, 2021, 2019]   # 2021 lands between, not at the top
    assert any(r["title"] == "Mid Paper" for r in rows)

def test_resort_raises_when_tbody_missing():
    import pytest
    with pytest.raises(ValueError):
        m.resort_tbody("<html><body>no table here</body></html>", [])

def test_resort_raises_on_malformed_new_row():
    import pytest
    html = load_fixture()
    with pytest.raises(ValueError):
        m.resort_tbody(html, ["<tr><td colspan=2>broken</td></tr>"])

def _crossref_item(title, type_, doi, journal, year):
    return {
        "title": [title],
        "type": type_,
        "DOI": doi,
        "container-title": [journal],
        "issued": {"date-parts": [[year]]},
    }

def test_crossref_match_accepts_close_journal_article():
    items = [_crossref_item(
        "Cholesterol-Conjugated Polyion Complex Nanoparticles for Colon Cancer",
        "journal-article", "10.3390/ijms26167965",
        "International Journal of Molecular Sciences", 2025)]
    r = m.crossref_best_match("Cholesterol Conjugated Polyion Complex Nanoparticles for Colon Cancer", items)
    assert r is not None
    assert r["doi"] == "10.3390/ijms26167965"
    assert r["journal"] == "International Journal of Molecular Sciences"
    assert r["year"] == "2025"

def test_crossref_match_rejects_non_journal_article():
    items = [_crossref_item("Some Conference Abstract", "proceedings-article",
                            "10.x/conf", "Proceedings of X", 2024)]
    assert m.crossref_best_match("Some Conference Abstract", items) is None

def test_crossref_match_rejects_low_similarity():
    items = [_crossref_item("A Totally Unrelated Paper On Quantum Gravity",
                            "journal-article", "10.x/qg", "Physics", 2024)]
    assert m.crossref_best_match("Liposomal Doxorubicin For Breast Cancer", items) is None

def test_crossref_match_empty_items():
    assert m.crossref_best_match("Anything", []) is None

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
