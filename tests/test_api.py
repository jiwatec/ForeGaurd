"""Real HTTP tests against a loopback-only server, without executing proposals."""

import http.client
import json
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from uuid import UUID

import uvicorn
from app.api import app
from app.store import Store


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.env = patch.dict("os.environ", {
            "FOREGUARD_DB_PATH": cls.temp.name + "/audit.sqlite3",
            "FOREGUARD_ADMIN_TOKEN": "local-test-secret",
        })
        cls.env.start()
        cls.socket = socket.socket()
        cls.socket.bind(("127.0.0.1", 0))
        cls.port = cls.socket.getsockname()[1]
        cls.server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False))
        cls.thread = threading.Thread(target=cls.server.run, kwargs={"sockets": [cls.socket]}, daemon=True)
        cls.thread.start()
        deadline = time.monotonic() + 5
        while not cls.server.started:
            if time.monotonic() > deadline:
                cls.server.should_exit = True
                raise RuntimeError("Test server did not start")
            time.sleep(0.01)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=5)
        cls.socket.close()
        cls.env.stop()
        cls.temp.cleanup()

    def request(self, method, path, payload=None, token=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            body = payload if isinstance(payload, str) else json.dumps(payload) if payload is not None else None
            headers = {"Content-Type": "application/json"}
            if token is not None:
                headers["Authorization"] = "Bearer " + token
            connection.request(method, path, body, headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def post(self, payload):
        return self.request("POST", "/api/commands/analyze", payload)

    def test_dashboard_serves_private_same_origin_assets(self):
        for path, expected in (("/review", "text/html"),
                               ("/review/app.js", "javascript"),
                               ("/review/style.css", "text/css")):
            with self.subTest(path=path):
                connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
                try:
                    connection.request("GET", path)
                    response = connection.getresponse()
                    body = response.read().decode()
                    self.assertEqual(response.status, 200)
                    self.assertIn(expected, response.getheader("Content-Type"))
                    self.assertEqual(response.getheader("Cache-Control"), "no-store")
                    self.assertIn("default-src 'none'", response.getheader("Content-Security-Policy"))
                    self.assertNotIn("local-test-secret", body)
                    if path.endswith("app.js"):
                        self.assertIn("textContent", body)
                finally:
                    connection.close()

    def test_decisions_and_contract(self):
        ids = set()
        for command, decision in (("uptime", "ALLOW"), ("mkdir test", "REVIEW"), ("dd of=/dev/sda", "BLOCK"), ("uptime\nrm -rf /", "REVIEW")):
            with self.subTest(command=command):
                status, body = self.post(dict(command=command, cwd="/tmp/foreguard-lab", source="test"))
                self.assertEqual(status, 200)
                self.assertEqual(body["decision"], decision)
                self.assertEqual(body["requires_approval"], decision == "REVIEW")
                self.assertEqual(set(body), {"request_id", "category", "risk_score", "decision", "reasons", "requires_approval"})
                UUID(body["request_id"])
                ids.add(body["request_id"])
        self.assertEqual(len(ids), 4)

    def test_bad_requests_block(self):
        base = dict(command="uptime", cwd="/tmp/lab", source="test")
        cases = ["{", {}, {**base, "command": 7}, {**base, "command": "a" * 4097}, {**base, "command": " "}, {**base, "cwd": "relative"}, {**base, "approve": True}]
        for payload in cases:
            with self.subTest(payload=payload):
                status, body = self.post(payload)
                self.assertEqual(status, 422)
                self.assertEqual(body["decision"], "BLOCK")
                self.assertFalse(body["requires_approval"])

    def test_backend_exception_blocks(self):
        with patch("app.store.assess_command", side_effect=RuntimeError("secret detail")):
            status, body = self.post(dict(command="uptime", cwd="/tmp/lab", source="test"))
        self.assertEqual(status, 500)
        self.assertEqual(body["decision"], "BLOCK")
        self.assertNotIn("secret detail", str(body))

    def test_review_auth_identity_and_persistence(self):
        identity = dict(command="mkdir private", cwd="/tmp/lab", source="agent")
        status, analyzed = self.post(identity)
        self.assertEqual(status, 200)
        request_id = analyzed["request_id"]
        path = f"/api/requests/{request_id}/decide"
        for token in (None, "wrong"):
            status, body = self.request("GET", "/api/requests", token=token)
            self.assertEqual((status, body["decision"]), (401, "BLOCK"))
            status, body = self.request("POST", path, {**identity, "decision": "APPROVE"}, token)
            self.assertEqual((status, body["decision"]), (401, "BLOCK"))
        with patch.dict("os.environ", {"FOREGUARD_ADMIN_TOKEN": ""}):
            status, body = self.request("GET", "/api/requests", token="local-test-secret")
            self.assertEqual((status, body["decision"]), (401, "BLOCK"))
        status, listing = self.request("GET", "/api/requests?limit=1&offset=0", token="local-test-secret")
        self.assertEqual(status, 200)
        self.assertEqual(listing["requests"][0]["id"], request_id)
        self.assertEqual(listing["requests"][0]["status"], "PENDING")
        status, body = self.request("POST", path, {**identity, "cwd": "/tmp/other", "decision": "APPROVE"}, "local-test-secret")
        self.assertEqual((status, body["decision"]), (409, "BLOCK"))
        status, body = self.request("POST", path, {**identity, "decision": "APPROVE"}, "local-test-secret")
        self.assertEqual((status, body["status"]), (200, "APPROVED"))
        status, body = self.request("POST", path, {**identity, "decision": "APPROVE"}, "local-test-secret")
        self.assertEqual((status, body["decision"]), (409, "BLOCK"))
        status, listing = self.request("GET", "/api/requests?limit=1", token="local-test-secret")
        self.assertEqual((status, listing["requests"][0]["status"]), (200, "APPROVED"))

    def test_block_expiry_and_pagination(self):
        identity = dict(command="rm -rf /", cwd="/tmp/lab", source="agent")
        _, body = self.post(identity)
        status, response = self.request("POST", f"/api/requests/{body['request_id']}/decide",
                                        {**identity, "decision": "APPROVE"}, "local-test-secret")
        self.assertEqual((status, response["decision"]), (409, "BLOCK"))
        for query in ("limit=101", "limit=0", "offset=-1"):
            status, response = self.request("GET", "/api/requests?" + query, token="local-test-secret")
            self.assertEqual((status, response["decision"]), (422, "BLOCK"))

        now = [1000.0]
        with patch("app.api.audit_store", side_effect=lambda: Store(
                self.temp.name + "/audit.sqlite3", clock=lambda: now[0])):
            review = dict(command="mkdir expiring", cwd="/tmp/lab", source="agent")
            status, created = self.post(review)
            self.assertEqual(status, 200)
            now[0] += 300
            status, response = self.request("POST", f"/api/requests/{created['request_id']}/decide",
                                            {**review, "decision": "APPROVE"}, "local-test-secret")
            self.assertEqual((status, response["decision"]), (409, "BLOCK"))
            status, listing = self.request("GET", "/api/requests", token="local-test-secret")
            record = next(row for row in listing["requests"] if row["id"] == created["request_id"])
            self.assertEqual((status, record["status"]), (200, "EXPIRED"))

    def test_storage_failure_blocks(self):
        with patch("app.api.audit_store", side_effect=RuntimeError("private detail")):
            status, body = self.post(dict(command="uptime", cwd="/tmp/lab", source="test"))
        self.assertEqual((status, body["decision"]), (500, "BLOCK"))
        self.assertNotIn("private detail", str(body))
