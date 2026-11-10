"""Assessment entry point: inspect text; never execute it."""

import json
import sys
from app.policy import assess, result


def assess_command(command: str) -> dict:
    """Return a decision for a command string without running it."""
    try:
        return assess(command)
    except Exception:
        return result("UNKNOWN", 100, "BLOCK", "Assessment failed; execution is not permitted")


if __name__ == "__main__":
    # Read the full input so a second line cannot be silently ignored.
    # Remove only the final Enter newline; other whitespace stays unrecognized.
    proposed_command = sys.stdin.read().removesuffix("\n")
    print(json.dumps(assess_command(proposed_command)))
