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

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
