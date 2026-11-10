"""Parser checks use command strings as data; none of them are executed."""

import unittest
from unittest.mock import patch

from app.parser import InvalidCommand, MAX_COMMAND_LENGTH, parse_command


class ParserTests(unittest.TestCase):
    def test_plain_commands_and_quoted_argument(self):
        self.assertEqual(parse_command("uptime"), ("uptime",))
        self.assertEqual(parse_command("ls -la"), ("ls", "-la"))
        self.assertEqual(parse_command("mkdir 'new folder'"), ("mkdir", "new folder"))
        self.assertEqual(parse_command("dd if=/dev/zero of=/dev/sda"),
                         ("dd", "if=/dev/zero", "of=/dev/sda"))

    def test_ambiguous_or_malformed_input_is_rejected(self):
        cases = (
            "", " ", " uptime", "uptime ", "uptime\nrm -rf /", "uptime\r", "uptime\x00",
            "uptime; rm -rf /", "uptime && rm -rf /", "uptime || rm -rf /",
            "uptime | cat", "uptime > output", "uptime < input", "uptime $(id)",
            "uptime `id`", "ls *", "ls ?", "ls [a-z]", "ls {a,b}",
            "uptime # comment", "ls ~/Documents", "uptime \\;", "'uptime",
            "echo 'hello;world'", "echo !", "a" * (MAX_COMMAND_LENGTH + 1),
            "''",
        )
        for command in cases:
            with self.subTest(command=command):
                with self.assertRaises(InvalidCommand):
                    parse_command(command)

    def test_non_string_input_is_rejected(self):
        for command in (None, 42, [], {}):
            with self.subTest(command=command):
                with self.assertRaises(InvalidCommand):
                    parse_command(command)

    def test_tokenizer_error_is_not_treated_as_valid(self):
        with patch("app.parser.shlex.split", side_effect=RuntimeError("tokenizer failed")):
            with self.assertRaises(InvalidCommand):
                parse_command("uptime")


if __name__ == "__main__":
    unittest.main()
