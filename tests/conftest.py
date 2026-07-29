"""Shared helpers for the SIM-006 test suite."""

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Load a test fixture JSON file by name.

    Args:
        name: Fixture file name, e.g. "event_all_pass.json".

    Returns:
        The parsed fixture payload.
    """
    with open(FIXTURES_DIR / name, encoding="utf-8") as fixture_file:
        return json.load(fixture_file)
