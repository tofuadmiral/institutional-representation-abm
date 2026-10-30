"""Prospective cached closure must match the immutable original algorithm."""
from pathlib import Path

import pytest

from paper3 import source_closure as reference
from paper3 import retrospective_source_closure as faster
from paper3 import retrospective_anticipation_freeze as freeze


def test_complete_candidate_closure_matches_original_inventory():
    root = Path(__file__).resolve().parents[1]
    roots = freeze.source_roots(root)
    assert faster.closure(root, roots) == reference.closure(root, roots)
    assert faster.closure(root, roots) == reference.closure(root, roots)


def test_newly_created_local_import_is_not_hidden_by_syntax_cache(tmp_path):
    entry = tmp_path / "entry.py"
    entry.write_text("import newly_local\nfrom pkg import nested\n")
    assert faster.closure(tmp_path, [entry]) == reference.closure(tmp_path, [entry]) == [entry]
    created = tmp_path / "newly_local.py"
    created.write_text("import other\n")
    assert created in faster.closure(tmp_path, [entry])
    assert faster.closure(tmp_path, [entry]) == reference.closure(tmp_path, [entry])
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "nested.py").write_text("from . import sibling\n")
    (package / "sibling.py").write_text("")
    assert faster.closure(tmp_path, [entry]) == reference.closure(tmp_path, [entry])
    assert package / "sibling.py" in faster.closure(tmp_path, [entry])


def test_changed_imports_and_deleted_sources_are_detected_on_every_call(tmp_path):
    entry = tmp_path / "entry.py"
    entry.write_text("import first\n")
    (tmp_path / "first.py").write_text("")
    (tmp_path / "second.py").write_text("")
    before = faster.closure(tmp_path, [entry])
    entry.write_text("import second\n")
    after = faster.closure(tmp_path, [entry])
    assert after != before and after == reference.closure(tmp_path, [entry])
    (tmp_path / "second.py").unlink()  # Own private fabricated source only.
    assert faster.closure(tmp_path, [entry]) == reference.closure(tmp_path, [entry]) == [entry]
    entry.unlink()
    with pytest.raises(ValueError, match="missing declared"):
        faster.closure(tmp_path, [entry])
