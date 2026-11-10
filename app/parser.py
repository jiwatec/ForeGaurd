"""Parse one simple command into arguments without executing it."""

import shlex


MAX_COMMAND_LENGTH = 4096
# Reject syntax with shell meaning, even inside quotes; conservative by design.
SHELL_SYNTAX = frozenset("|&;<>()$`*?[]{}\\#!~")


class InvalidCommand(ValueError):
    """Input cannot be safely treated as one plain command."""


def parse_command(command: str) -> tuple[str, ...]:
    """Return arguments for one plain command, or raise InvalidCommand.

    Parsing is not a security decision. The returned arguments are still untrusted.
    """
    if not isinstance(command, str) or not command or command != command.strip():
        raise InvalidCommand("Command must be a non-empty string without outer whitespace")
    if len(command) > MAX_COMMAND_LENGTH:
        raise InvalidCommand("Command is too long")
    if any(ord(char) < 32 or ord(char) == 127 for char in command):
        raise InvalidCommand("Control characters are not supported")
    if any(char in SHELL_SYNTAX for char in command):
        raise InvalidCommand("Shell syntax is not supported")

    try:
        arguments = shlex.split(command, posix=True)
    except Exception as exc:
        raise InvalidCommand("Command cannot be parsed") from exc

    if not arguments or not arguments[0]:
        raise InvalidCommand("Command name is missing")
    return tuple(arguments)
