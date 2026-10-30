"""Actual outer-audit regression with PRIVATE fabricated network evidence only."""
import pytest

from analysis import paper3_validation_audit_v1 as helper
from experiments import paper3_independent_validation_v1 as r
from tests.test_paper3_independent_validation_v1 import fixture


def test_exact_outer_production_audit_and_lossless_summary_decode(tmp_path, monkeypatch):
    root, protocol, sent, send, lookup, book = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(book, '_entries', lambda: [r.load(p)
        for p in (book.root/'entries').glob('*.json')], raising=False)
    assert r.run(root, protocol, send=send, lookup=lookup)['status'] == 'complete'
    assert len(sent) == 481
    # Preserve/prove the frozen original summary bug rather than weakening its
    # full report comparison or rewriting the already-prepared source closure.
    with pytest.raises(KeyError, match='validation'):
        r.audit(root, protocol)
    result = helper.audit(root, protocol)
    assert result['entire_report_matched']
    assert result['validation']['independent_fresh_assignments']
    assert len(sent) == 481  # Neither audit reissues any model/receipt request.
