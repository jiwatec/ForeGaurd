"""Phase 1 learning prototype: assess text; never execute it."""

import json
import sys


# Exact examples only. Scores are illustrative, not measured risk predictions.
EXAMPLES = {
    "uptime": ("READ", 0, "ALLOW", "Exact read-only example"),
    "ls -la": ("READ", 0, "ALLOW", "Exact read-only example"),
    "mkdir test": ("WRITE", 25, "REVIEW", "Creates a directory"),
    "rm file.txt": ("WRITE", 55, "REVIEW", "Deletes a file"),
    "rm -rf /": ("FORBIDDEN", 100, "BLOCK", "Destructive root deletion"),
    "dd": ("FORBIDDEN", 100, "BLOCK", "Disk-writing tool is forbidden"),
}


def assess_command(command: str) -> dict:
    """Return a decision for a command string without running it."""
    if not isinstance(command, str) or not command.strip():
        return {
            "category": "UNKNOWN",
            "risk_score": 100,
            "decision": "BLOCK",
            "reasons": ["Command must be a non-empty string"],
        }

    if command in EXAMPLES:
        category, score, decision, reason = EXAMPLES[command]
        return {
            "category": category,
            "risk_score": score,
            "decision": decision,
            "reasons": [reason],
        }

    return {
        "category": "UNKNOWN",
        "risk_score": 70,
        "decision": "REVIEW",
        "reasons": ["Unrecognized or ambiguous command; no automatic permission"],
    }


if __name__ == "__main__":
    # Read the full input so a second line cannot be silently ignored.
    # Remove only the final Enter newline; other whitespace stays unrecognized.
    proposed_command = sys.stdin.read().removesuffix("\n")
    print(json.dumps(assess_command(proposed_command)))
