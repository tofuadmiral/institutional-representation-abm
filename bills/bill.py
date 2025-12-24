from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass
class Bill:
    """
    Minimal representation of a policy proposal considered by the legislature.

    The ideology vector locates the bill in an abstract policy space, while
    salience indicates how important the bill is relative to other issues.
    """

    bill_id: int
    ideology: Sequence[float]
    salience: float


