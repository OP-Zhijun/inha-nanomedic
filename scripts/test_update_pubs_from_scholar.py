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

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
