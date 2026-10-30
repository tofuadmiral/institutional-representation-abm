"""Offline invariance and rejection checks for the unlaunched mask interface."""
import itertools
import json
import unittest

from paper3 import coalition_contracts as game
from paper3 import constituent_b_institution as original
from paper3 import constituent_b_masked_institution as masked
from paper3 import constituent_b_repeatability_design as design


def offer(coalition, stage):
    answer = dict(projects=dict(A="A0", B="B0"), first="A",
                  coalition_mask=[actor in coalition for actor in game.ACTORS],
                  message="scripted")
    if stage == "response":
        answer["support"] = True
    return answer


class MaskedInstitutionTests(unittest.TestCase):
    def test_every_legal_coalition_maps_exactly(self):
        for stage in ("draft", "response", "final"):
            for coalition in ((), *itertools.combinations(game.ACTORS, 4)):
                parsed = masked.parse_action(json.dumps(offer(coalition, stage)), stage)
                self.assertEqual(parsed["coalition"], list(coalition))
                self.assertNotIn("coalition_mask", parsed)

    def test_bad_masks_and_duplicate_keys_fail_without_repair(self):
        valid = offer((0, 1, 2, 3), "draft")
        masks = ([True] * 3 + [False] * 4,
                 [True] * 5 + [False] * 2,
                 [True] * 4 + [False] * 2,
                 [True] * 4 + [False] * 4,
                 [1] * 4 + [False] * 3,
                 "0,1,2,3")
        for mask in masks:
            with self.subTest(mask=mask), self.assertRaises(ValueError):
                masked.parse_action(json.dumps(dict(valid, coalition_mask=mask)), "draft")
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            masked.parse_action('{"projects":{},"first":"A","coalition_mask":[],"coalition_mask":[],"message":"x"}', "draft")
        with self.assertRaises(ValueError):
            masked.parse_action(json.dumps(dict(valid, coalition=[0, 1, 2, 3])), "draft")

    def test_only_offer_prompts_change(self):
        prepared = design.profiles()[0]["prepared"]
        proposer = prepared["contract_profile"]["proposer"]
        for arm in game.ARMS:
            for stage in ("draft", "response"):
                before = original.messages(prepared, arm, proposer, stage, [])
                after = masked.messages(prepared, arm, proposer, stage, [])
                self.assertEqual(before[0], after[0])
                self.assertIn("coalition_mask is an array of seven booleans",
                              after[1]["content"])
                self.assertNotIn("coalition is an array of four",
                                 after[1]["content"])
            self.assertEqual(original.messages(prepared, arm, proposer, "consent", []),
                             masked.messages(prepared, arm, proposer, "consent", []))

    def test_complete_episode_matches_historical_controller(self):
        prepared = design.profiles()[0]["prepared"]
        for arm in game.ARMS:
            def answer(actor, stage, messages, index, use_mask):
                if stage in ("draft", "response", "final"):
                    row = offer((0, 1, 2, 3), stage)
                    if not use_mask:
                        row["coalition"] = [0, 1, 2, 3]
                        del row["coalition_mask"]
                elif stage == "consent":
                    row = dict(consent=True)
                else:
                    row = dict(vote=True)
                return json.dumps(row)

            historical = original.episode(
                prepared, arm, lambda a, s, m, i: answer(a, s, m, i, False))
            candidate = masked.episode(
                prepared, arm, lambda a, s, m, i: answer(a, s, m, i, True))
            self.assertEqual(candidate, historical)


if __name__ == "__main__":
    unittest.main()
