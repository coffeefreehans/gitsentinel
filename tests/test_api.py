import os
import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import app

class TestAPIEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_get_repos(self):
        res = self.client.get("/api/repos")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("repos", data)
        self.assertIn("global_hooks_enabled", data)

    def test_get_keys(self):
        res = self.client.get("/api/keys")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("keys", data)
        self.assertIn("git_user", data)

    def test_get_notifications(self):
        res = self.client.get("/api/notifications")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("notifications", data)

    def test_get_settings(self):
        res = self.client.get("/api/settings")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("security_rules", data)

    def test_static_index(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("GitSentinel", res.text)

if __name__ == "__main__":
    unittest.main()
