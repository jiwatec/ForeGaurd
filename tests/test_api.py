"""Real HTTP tests against a loopback-only server, without executing proposals."""

import http.client
import json
import socket
import threading
import time
import unittest
from unittest.mock import patch
from uuid import UUID

import uvicorn
from app.api import app


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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

    def post(self, payload):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            body = payload if isinstance(payload, str) else json.dumps(payload)
            connection.request("POST", "/api/commands/analyze", body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
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
        with patch("app.api.assess_command", side_effect=RuntimeError("secret detail")):
            status, body = self.post(dict(command="uptime", cwd="/tmp/lab", source="test"))
        self.assertEqual(status, 500)
        self.assertEqual(body["decision"], "BLOCK")
        self.assertNotIn("secret detail", str(body))
