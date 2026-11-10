import unittest
from unittest.mock import patch

from app.classifier import assess_command


class PolicyTests(unittest.TestCase):
    def test_forbidden_variants(self):
        for command in ("dd if=/dev/zero of=/dev/sda", "/bin/dd of=disk", "rm -fr /", "rm --recursive test", "rm /etc/passwd", "mkfs.ext4 /dev/sda", "reboot"):
            with self.subTest(command=command):
                self.assertEqual(assess_command(command)["decision"], "BLOCK")

    def test_allowlist_cannot_be_expanded_by_parsing(self):
        for command in ("'uptime'", "/bin/uptime", "sudo uptime", "env uptime", "uptime --help", "uptime; id", "sh -c 'uptime'", "ls -la /etc", "uptime\nrm -rf /"):
            with self.subTest(command=command):
                self.assertNotEqual(assess_command(command)["decision"], "ALLOW")

    def test_policy_failure_blocks(self):
        with patch("app.classifier.assess", side_effect=RuntimeError("private details")):
            result = assess_command("uptime")
        self.assertEqual(result["decision"], "BLOCK")
        self.assertNotIn("private details", str(result))

    def test_parser_failure_never_allows(self):
        with patch("app.parser.shlex.split", side_effect=RuntimeError("failure")):
            self.assertNotEqual(assess_command("uptime")["decision"], "ALLOW")
