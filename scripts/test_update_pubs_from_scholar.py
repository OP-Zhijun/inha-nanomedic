import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update_pubs_from_scholar as m

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "sample_table.html")

def load_fixture():
    with open(FIX, encoding="utf-8") as f:
        return f.read()

# tests are added in later tasks

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
