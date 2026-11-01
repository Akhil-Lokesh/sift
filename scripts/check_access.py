"""Confirm API keys work and the pinned models exist.

Only calls the model-listing endpoints, which are not billed per token.
Usage: uv run python scripts/check_access.py
"""

import os
import sys

import anthropic
from dotenv import load_dotenv
from typesafe_sdk import TypeSafeClient

from sift.pricing import DECISION_MODEL, MENU


def check_claude() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("claude: ANTHROPIC_API_KEY not set")
        return False
    try:
        available = {m.id for m in anthropic.Anthropic().models.list()}
    except anthropic.AuthenticationError:
        print("claude: key rejected")
        return False
    except anthropic.APIConnectionError as e:
        print(f"claude: connection failed: {e}")
        return False
    ok = True
    for role, model in MENU.items():
        found = model in available
        ok &= found
        print(f"claude: {role:<6} {model:<20} {'ok' if found else 'MISSING'}")
    return ok


def check_jev() -> bool:
    if not os.environ.get("TYPESAFE_API_KEY"):
        print("jev: TYPESAFE_API_KEY not set")
        return False
    try:
        with TypeSafeClient() as client:
            listing = client.models.list()
    except Exception as e:  # SDK exception classes not yet pinned down; report and move on
        print(f"jev: request failed: {type(e).__name__}: {e}")
        return False
    names = {m.name for m in listing.models}
    found = DECISION_MODEL in names
    print(f"jev: {DECISION_MODEL} {'ok' if found else 'MISSING'} (available: {sorted(names)})")
    return found


if __name__ == "__main__":
    load_dotenv()
    results = [check_claude(), check_jev()]
    sys.exit(0 if all(results) else 1)
