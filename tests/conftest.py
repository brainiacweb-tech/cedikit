from pathlib import Path
from typing import Any

import pytest
import yaml

FIXTURES = Path(__file__).parent / "fixtures" / "sample_messages"


def _load(name: str) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = yaml.safe_load((FIXTURES / name).read_text("utf-8"))
    return data


@pytest.fixture(scope="session")
def genuine() -> dict[str, dict[str, Any]]:
    return {s["id"]: s for s in _load("genuine.yaml")}


@pytest.fixture(scope="session")
def scam() -> dict[str, dict[str, Any]]:
    return {s["id"]: s for s in _load("scam.yaml")}
