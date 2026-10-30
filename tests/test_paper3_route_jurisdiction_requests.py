"""No-spend request and reservation preflight for the proposed route gate."""
from decimal import Decimal
import unittest

from paper3 import route_jurisdiction_requests as requests


class RouteJurisdictionRequestTests(unittest.TestCase):
    def test_stage_schemas_leave_every_legal_action_available(self):
        for stage in ("recommendation", "offer", "ballot", "review"):
            schema = requests.action_schema(stage)
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(set(schema["required"]), set(schema["properties"]))
        self.assertEqual(set(requests.action_schema("offer")["properties"]["route"]["enum"]),
                         {"floor", "committee"})
        self.assertEqual(set(requests.action_schema("offer")["properties"]["policy_id"]["enum"]),
                         {"q", "p0", "p1", "p2"})
        self.assertEqual(requests.action_schema("ballot")["properties"]["yes"]["type"], "boolean")
        with self.assertRaises(ValueError):
            requests.action_schema("unknown")

    def test_twelve_requests_pinned_native_and_under_proposed_cap(self):
        rows = requests.gate_requests()
        self.assertEqual(len(rows), 12)
        self.assertEqual(len({r["seed"] for r in rows}), 12)
        self.assertEqual({r["seed"] for r in rows}, set(range(362000, 362012)))
        self.assertLess(sum(Decimal(r["reserved_usd"]) for r in rows), requests.GATE_CAP)
        for row in rows:
            req = row["request"]
            self.assertEqual(req["model"], requests.MODEL)
            self.assertEqual(req["max_tokens"], 8192)
            self.assertEqual(req["reasoning"], dict(enabled=True, exclude=False))
            self.assertEqual(req["provider"]["only"], [requests.PROVIDER_TAG])
            self.assertFalse(req["provider"]["allow_fallbacks"])
            self.assertEqual(req["response_format"]["type"], "json_schema")
            self.assertLessEqual(row["input_token_bound"], requests.INPUT_BOUND)
            self.assertEqual(row["wire"], requests.reservation(req)["wire"])

    def test_invalid_request_and_bound_rejected(self):
        with self.assertRaises(ValueError):
            requests.request([], -1, kind="rule")
        with self.assertRaises(ValueError):
            requests.request([], 1, kind="rule", stage="offer")
        with self.assertRaises(ValueError):
            requests.request([], 1, kind="action", stage="bad")
        with self.assertRaises(ValueError):
            requests.reservation(dict(messages=[dict(content="x" * 12000)]))

    def test_pilot_schedule_and_scripted_size_preflight(self):
        assignments = requests.pilot_assignments()
        self.assertEqual(len(assignments), 8)
        self.assertEqual({(a["profile"]["name"], a["arm"]) for a in assignments},
                         {(p["name"], arm) for p in requests.design.frame()
                          if p["split"] == "discovery_candidate" for arm in requests.game.ARMS})
        seeds = {a["seed_base"] + j for a in assignments for j in range(16)}
        self.assertEqual(seeds, set(range(363000, 363128)))
        report = requests.scripted_pilot_preflight()
        self.assertEqual(report["intended_calls"], 128)
        self.assertLess(report["maximum_input_bound"], requests.INPUT_BOUND)
        self.assertLess(Decimal(report["scripted_path_reservations_usd"]), requests.PILOT_CAP)


if __name__ == "__main__":
    unittest.main()
