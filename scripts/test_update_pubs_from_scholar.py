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

def test_crossref_match_prefers_journal_article_over_preprint():
    # Crossref often returns a preprint (posted-content) AND the final journal
    # article for the same title. The journal article must win even when the
    # preprint is listed first with an equal title score (review finding).
    items = [
        _crossref_item("Targeted Nanoparticles For Colon Cancer", "posted-content",
                       "10.1101/preprint", "bioRxiv", 2024),
        _crossref_item("Targeted Nanoparticles For Colon Cancer", "journal-article",
                       "10.3390/final", "ACS Nano", 2025),
    ]
    r = m.crossref_best_match("Targeted Nanoparticles For Colon Cancer", items)
    assert r is not None
    assert r["doi"] == "10.3390/final"
    assert r["journal"] == "ACS Nano"

def test_crossref_match_excludes_ssrn_preprint_only():
    # SSRN registers preprints as type "journal-article"; exclude them so the
    # site stays peer-reviewed-only.
    items = [_crossref_item("Cancer Stem Cell Photodynamic Therapy", "journal-article",
                            "10.2139/ssrn.3873675", "SSRN Electronic Journal", 2021)]
    assert m.crossref_best_match("Cancer Stem Cell Photodynamic Therapy", items) is None

def test_crossref_match_prefers_real_journal_over_ssrn():
    items = [
        _crossref_item("Cancer Stem Cell Photodynamic Therapy", "journal-article",
                       "10.2139/ssrn.3873675", "SSRN Electronic Journal", 2021),
        _crossref_item("Cancer Stem Cell Photodynamic Therapy", "journal-article",
                       "10.1016/j.jconrel.real", "Journal of Controlled Release", 2022),
    ]
    r = m.crossref_best_match("Cancer Stem Cell Photodynamic Therapy", items)
    assert r is not None and r["doi"] == "10.1016/j.jconrel.real"

def test_manual_review_reason_flags_allcaps_and_section_artifact():
    assert m.manual_review_reason(
        "PROTECTIVE EFFECT OF TPP-NIACIN ON MICROGRAVITY-INDUCED OXIDATIVE STRESS") is not None
    assert m.manual_review_reason(
        "Bioavailability Section-Stable bioavailability of cyclosporin A from capsules") is not None
    # a normal mixed-case title is NOT held
    assert m.manual_review_reason(
        "MT1-MMP Responsive Doxorubicin Conjugated Microparticles") is None

def test_update_counters_meta_description():
    pub = '<meta name="description" content="96 peer-reviewed publications in nanomedicine.">'
    out_pub, _ = m.update_counters(pub, "", 98)
    assert "98 peer-reviewed publications" in out_pub
    assert "96 peer-reviewed" not in out_pub

def test_update_counters_index_stats_bar():
    index = (
        '<div class="stat-number" data-count="96">96</div>\n'
        '            <div class="stat-label">Publications</div>'
    )
    _, out_index = m.update_counters("", index, 98)
    assert 'data-count="98"' in out_index
    assert 'data-count="96"' not in out_index

def test_update_counters_only_publications_stat_and_keeps_suffix():
    # mirrors the REAL index.html: 3 stats, Publications carries data-suffix=""
    index = (
        '      <div class="stat-number" data-count="20" data-suffix="+">0</div>\n'
        '      <div class="stat-label">Years of Research</div>\n'
        '      <div class="stat-number" data-count="96" data-suffix="">0</div>\n'
        '      <div class="stat-label">Publications</div>\n'
        '      <div class="stat-number" data-count="3" data-suffix="">0</div>\n'
        '      <div class="stat-label">Research Areas</div>\n'
    )
    _, out = m.update_counters("", index, 98)
    assert 'data-count="98" data-suffix=""' in out   # publications bumped, suffix kept
    assert 'data-count="20" data-suffix="+"' in out   # Years untouched
    assert 'data-count="3" data-suffix=""' in out     # Research Areas untouched

def test_already_on_site_catches_title_drift():
    existing = [m.normalize("Beta-Lapachone Micellar Nanotherapeutics for Non-Small Cell Lung Cancer Therapy")]
    cand = m.normalize("β-Lapachone micellar nanotherapeutics for non–small cell lung cancer therapy")
    assert m.already_on_site(cand, existing) is True

def test_already_on_site_allows_genuinely_new():
    existing = [m.normalize("A Study Of Liposomes For Breast Cancer")]
    cand = m.normalize("Photothermal Gold Nanorods For Colon Cancer Immunotherapy")
    assert m.already_on_site(cand, existing) is False

def test_frozen_rows_returns_pre_min_year_only_in_order():
    rows = [
        {"raw": "<tr>A2025</tr>", "year": 2025},
        {"raw": "<tr>B2024</tr>", "year": 2024},
        {"raw": "<tr>C2010</tr>", "year": 2010},
    ]
    assert m.frozen_rows(rows, 2025) == ["<tr>B2024</tr>", "<tr>C2010</tr>"]

def test_build_new_rows_doi_link_and_escaping():
    papers = [{"title": "Nano & Cancer <Study>", "journal": "ACS Nano",
               "year": "2025", "doi": "10.1/xyz"}]
    rows = m.build_new_rows(papers)
    assert len(rows) == 1
    row = rows[0]
    assert "Nano &amp; Cancer &lt;Study&gt;" in row     # escaped
    assert 'href="https://doi.org/10.1/xyz"' in row
    assert 'rel="noopener noreferrer"' in row           # qa_check.py requires this
    assert row.startswith("<tr><td>") and row.endswith("</tr>")

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
