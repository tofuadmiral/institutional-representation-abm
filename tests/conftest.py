from __future__ import annotations

import sys
from pathlib import Path

# Make the repo root importable so tests can `import config`, `import institutions`, ...
REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from config import ParliamentaryConfig, RepublicanConfig
from institutions.parliamentary import ParliamentaryModel
from institutions.republican import RepublicanModel


@pytest.fixture
def parliamentary_model():
    return ParliamentaryModel(
        num_legislators=20,
        num_constituencies=6,
        num_parties=3,
        config=ParliamentaryConfig(),
        seed=42,
    )


@pytest.fixture
def republican_model():
    return RepublicanModel(
        num_legislators=20,
        num_constituencies=6,
        num_parties=3,
        config=RepublicanConfig(),
        seed=42,
    )
