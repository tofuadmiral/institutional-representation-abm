"""Pure shared-prefix shock branching for a prospective release-right study.

Within one announced institution, the two shock realizations reuse exactly
the same 22 agent-authored decisions made before the state is revealed. The
seven post-shock Y ballots are elicited separately for each state. Distinct
institutions must run their own prefixes; this module makes no model calls.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Callable

from paper3 import mandate_release_institution as institution
from paper3 import mandate_release_rival_opportunity as opportunity


Decision = Callable[[int, str, dict[str, object], bool | None], object]
Completed = Callable[[bool, institution.Episode], None]


def episode_pair(game: opportunity.RivalWitness, arm: str, proposer: int,
                 ask: Decision, on_complete: Completed | None = None
                 ) -> tuple[institution.Episode, institution.Episode]:
    """Return no-shock and shock episodes from one arm-specific prefix.

    ``ask`` receives ``None`` for a pre-shock decision and a bool for a
    post-shock Y ballot. Prefix choices are never re-elicited or silently
    recomputed for the second realization. The replay checks that the
    controller supplied exactly the same pre-shock context both times.
    """
    if arm not in institution.ARMS or proposer not in institution.ACTORS:
        raise ValueError("arm or proposer")
    decisions: dict[tuple[str, int], object] = {}
    contexts: dict[tuple[str, int], dict[str, object]] = {}
    ballots: dict[bool, int] = {False: 0, True: 0}

    def one(shocked: bool) -> institution.Episode:
        def choose(actor: int, stage: str, context: dict[str, object]) -> object:
            if stage == "y_vote":
                ballots[shocked] += 1
                return ask(actor, stage, context, shocked)
            key = (stage, actor)
            if key in decisions:
                if deepcopy(context) != contexts[key]:
                    raise ValueError("pre-shock context diverged across branches")
                return deepcopy(decisions[key])
            if shocked:
                raise ValueError("new pre-shock decision in second branch")
            contexts[key] = deepcopy(context)
            decisions[key] = deepcopy(ask(actor, stage, context, None))
            return deepcopy(decisions[key])

        result = institution.episode(game, arm, shocked, proposer, choose)
        if on_complete is not None:
            on_complete(shocked, result)
        return result

    unshocked, shocked = one(False), one(True)
    if len(decisions) != 22 or ballots != {False: 7, True: 7}:
        raise ValueError("branch decision inventory")
    return unshocked, shocked
