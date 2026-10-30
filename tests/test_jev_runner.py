import json
import pytest
from jev_study.bill_choice import make_cases
from jev_study.run import wire_request, read_key


def test_wire_keeps_order_manipulation_even_after_manifest_roundtrip():
    a, b = make_cases()[:2]
    wires = [wire_request(a), wire_request(b)]
    restored = json.loads(json.dumps({"wire_requests": wires}, sort_keys=True))["wire_requests"]
    orders = [list(json.loads(w)["questions"]["bill"]["criteria"]) for w in restored]
    assert orders[0] == list(reversed(orders[1]))


def test_key_loading_never_guesses_unlabelled_key(tmp_path):
    path = tmp_path / "test-key"
    path.write_text("synthetic-not-a-real-key")
    with pytest.raises(ValueError):
        read_key(path)
    assert read_key(path, True) == "synthetic-not-a-real-key"
    path.write_text('typesafe_api_key="synthetic-not-a-real-key"')
    assert read_key(path) == "synthetic-not-a-real-key"
    path.write_text('typesafe_ai_key = «synthetic-not-a-real-key»')
    assert read_key(path) == "synthetic-not-a-real-key"
    path.write_text('typsafe_ai_key = "synthetic-not-a-real-key"')
    assert read_key(path) == "synthetic-not-a-real-key"
