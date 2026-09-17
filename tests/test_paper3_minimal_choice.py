import json

from experiments.paper3_minimal_choice_audit import choice_case


def test_minimal_choices_are_balanced_and_equivalent_across_encodings():
    for actor in (2, 5):
        for sign in (-1, 1):
            for table in ("own", "all"):
                boolean, _, expected_bool = choice_case(actor, sign, table, "boolean")
                label, _, expected_label = choice_case(actor, sign, table, "label")
                assert boolean[0] == label[0]
                payload = boolean[1]["content"].split("\n")[0]
                assert payload == label[1]["content"].split("\n")[0]
                record = json.loads(payload)
                assert len(record["utilities_by_principal"]) == (1 if table == "own" else 7)
                gain = sum(record["utilities_by_principal"][str(actor)].values())
                assert gain == expected_bool["principal_utility_if_accepted"] == expected_label["principal_utility_if_accepted"]
                assert expected_bool["accept"] == (gain > 0)
                assert expected_label["action"] == ("accept" if gain > 0 else "decline")
