"""Tests for health check endpoints."""
from unittest.mock import patch, MagicMock

from django.test import TestCase


class TestHealthLive(TestCase):
    def test_returns_200(self):
        response = self.client.get("/api/health/live/")
        self.assertEqual(response.status_code, 200)

    def test_payload(self):
        response = self.client.get("/api/health/live/")
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["check"], "live")
        self.assertEqual(data["app"], "SNSA")

    def test_no_auth_required(self):
        # Must be accessible without login (probe runs before app is fully up)
        response = self.client.get("/api/health/live/")
        self.assertNotEqual(response.status_code, 403)
        self.assertNotEqual(response.status_code, 401)


class TestHealthReady(TestCase):
    def test_returns_200_when_db_ok(self):
        # In-memory SQLite is always available in tests
        response = self.client.get("/api/health/ready/")
        self.assertEqual(response.status_code, 200)

    def test_payload_when_db_ok(self):
        response = self.client.get("/api/health/ready/")
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["check"], "ready")
        self.assertEqual(data["db"], "ok")
        self.assertEqual(data["app"], "SNSA")

    def test_no_auth_required(self):
        response = self.client.get("/api/health/ready/")
        self.assertNotEqual(response.status_code, 403)
        self.assertNotEqual(response.status_code, 401)

    def test_returns_503_when_db_unavailable(self):
        from django.db.utils import OperationalError

        with patch("apps.core.views.connection") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.execute.side_effect = OperationalError("connection refused")
            mock_conn.cursor.return_value = mock_cursor

            response = self.client.get("/api/health/ready/")

        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["db"], "unavailable")
        self.assertIn("detail", data)
