from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from app.store import ApprovalError, Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "audit.sqlite3"
        self.now = 1000.0
        self.store = Store(self.path, clock=lambda: self.now)
        self.identity = dict(command="mkdir test", cwd="/tmp/lab", source="test-agent")

    def submit(self):
        return self.store.submit(**self.identity)

    def test_persists_assessment_and_history(self):
        request = self.submit()
        reopened = Store(self.path, clock=lambda: self.now)
        self.assertEqual(reopened.get(request)["assessment"]["decision"], "REVIEW")
        self.assertEqual(reopened.history()[0]["command"], "mkdir test")
        self.assertEqual(reopened.events(request), [{"kind": "ASSESSED", "timestamp": self.now}])

    def test_approve_and_reject_are_single_use(self):
        for decision, expected in (("APPROVE", "APPROVED"), ("REJECT", "REJECTED")):
            request = self.submit()
            result = self.store.decide(request, decision, **self.identity)
            self.assertEqual(result["status"], expected)
            with self.assertRaises(ApprovalError):
                self.store.decide(request, "APPROVE", **self.identity)
            self.assertEqual(self.store.events(request)[-1]["kind"], expected)

    def test_block_and_allow_cannot_be_approved(self):
        for command in ("rm -rf /", "uptime"):
            identity = {**self.identity, "command": command}
            request = self.store.submit(**identity)
            with self.assertRaises(ApprovalError):
                self.store.decide(request, "APPROVE", **identity)

    def test_exact_binding(self):
        request = self.submit()
        for field in self.identity:
            with self.subTest(field=field), self.assertRaises(ApprovalError):
                self.store.decide(request, "APPROVE", **{**self.identity, field: "changed"})
        self.assertEqual(self.store.get(request)["status"], "PENDING")

    def test_expiry_at_boundary_is_persisted(self):
        request = self.submit()
        self.now += 300
        self.assertEqual(self.store.get(request)["status"], "EXPIRED")
        with self.assertRaises(ApprovalError):
            self.store.decide(request, "APPROVE", **self.identity)
        self.assertEqual(self.store.events(request)[-1]["kind"], "EXPIRED")

    def test_concurrent_decisions_have_one_winner(self):
        request = self.submit()
        def attempt(_):
            try:
                self.store.decide(request, "APPROVE", **self.identity)
                return True
            except ApprovalError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(attempt, range(2))), 1)
        self.assertEqual(len(self.store.events(request)), 2)

    def test_invalid_and_missing_requests(self):
        with self.assertRaises(ApprovalError):
            self.store.decide("missing", "APPROVE", **self.identity)
        with self.assertRaises(ValueError):
            self.store.history(limit=1000)
        with self.assertRaises(ValueError):
            self.store.submit(**self.identity, ttl=-1)
