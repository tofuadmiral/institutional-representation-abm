import json

from paper3.logrolling import LinkInstitution, complementary_scenario, run_linked_vote_probe


class Backend:
    model = "test"

    def __init__(self, replies):
        self.replies = iter(replies)

    def generate(self, messages, *, temperature=0.0, max_tokens=256):
        return next(self.replies)


def test_portfolio_link_can_pass_bills_that_separate_votes_fail():
    scenario = complementary_scenario()
    replies = [
        json.dumps({"sign": True, "vote_bill_a": True, "vote_bill_b": False}),
        json.dumps({"sign": True, "vote_bill_a": True, "vote_bill_b": False}),
        json.dumps({"sign": True, "vote_bill_a": False, "vote_bill_b": True}),
        json.dumps({"sign": True, "vote_bill_a": False, "vote_bill_b": True}),
    ]
    linked = run_linked_vote_probe(scenario=scenario, institution=LinkInstitution.VOLUNTARY_PORTFOLIO_LINK, backend=Backend(replies))
    assert linked["decision"]["linked"]
    assert linked["decision"]["enacted_bill_a"] and linked["decision"]["enacted_bill_b"]
