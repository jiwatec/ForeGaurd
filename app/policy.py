"""Deterministic, assessment-only policy. Scores are policy weights, not probabilities."""

from pathlib import PurePosixPath

from app.parser import InvalidCommand, parse_command


def result(category, score, decision, reason):
    return dict(category=category, risk_score=score, decision=decision, reasons=[reason])


def assess(command):
    if not isinstance(command, str) or not command.strip():
        return result("UNKNOWN", 100, "BLOCK", "Expected a non-empty command string")
    try:
        argv = parse_command(command)
    except InvalidCommand:
        # REVIEW is not permission to execute unsupported syntax.
        return result("UNKNOWN", 90, "REVIEW", "Unsupported or malformed command; execution is not permitted")

    executable = PurePosixPath(argv[0]).name
    if executable in {"dd", "mkfs", "wipefs", "shutdown", "reboot", "halt", "poweroff"} or executable.startswith("mkfs."):
        return result("FORBIDDEN", 100, "BLOCK", "System-destructive operation is forbidden")
    if executable == "rm":
        flags = [arg for arg in argv[1:] if arg.startswith("-")]
        recursive = any(arg in {"--recursive"} or (arg.startswith("-") and not arg.startswith("--") and "r" in arg.lower()) for arg in flags)
        critical = any(arg == "/" or arg.startswith(("/etc", "/dev", "/boot", "/usr", "/proc", "/sys")) for arg in argv[1:])
        if recursive or critical:
            return result("FORBIDDEN", 100, "BLOCK", "Recursive or critical-path deletion is forbidden")
        return result("WRITE", 55, "REVIEW", "Deletion requires review")
    # Keep the automatic surface exact: parsing never widens the allowlist.
    if command in {"uptime", "ls -la"}:
        return result("READ", 0, "ALLOW", "Exact diagnostic command in the allowlist")
    if argv[0] in {"mkdir", "touch", "cp", "mv", "chmod", "chown"}:
        return result("WRITE", 40, "REVIEW", "Filesystem modification requires review")
    return result("UNKNOWN", 70, "REVIEW", "Command or arguments outside the automatic allowlist")
