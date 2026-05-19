"""Tests for IP resolution utility (apps.core.ip_utils)."""
from unittest.mock import patch

from django.test import TestCase, RequestFactory

from apps.core.ip_utils import parse_trusted_cidrs, is_trusted_proxy, get_client_ip


class TestParseTrustedCidrs(TestCase):
    def test_empty_string_returns_empty(self):
        with self.settings(TRUSTED_PROXY_CIDRS=""):
            self.assertEqual(parse_trusted_cidrs(), [])

    def test_single_cidr(self):
        with self.settings(TRUSTED_PROXY_CIDRS="10.0.0.0/8"):
            cidrs = parse_trusted_cidrs()
            self.assertEqual(len(cidrs), 1)

    def test_multiple_cidrs_space_separated(self):
        with self.settings(TRUSTED_PROXY_CIDRS="10.0.0.0/8 172.16.0.0/12"):
            cidrs = parse_trusted_cidrs()
            self.assertEqual(len(cidrs), 2)

    def test_multiple_cidrs_comma_separated(self):
        with self.settings(TRUSTED_PROXY_CIDRS="10.0.0.0/8,172.16.0.0/12"):
            cidrs = parse_trusted_cidrs()
            self.assertEqual(len(cidrs), 2)

    def test_invalid_cidr_is_skipped(self):
        with self.settings(TRUSTED_PROXY_CIDRS="10.0.0.0/8 not-a-cidr"):
            cidrs = parse_trusted_cidrs()
            self.assertEqual(len(cidrs), 1)


class TestIsTrustedProxy(TestCase):
    def setUp(self):
        import ipaddress
        self.cidrs = [ipaddress.ip_network("10.128.0.0/14")]

    def test_ip_within_cidr_is_trusted(self):
        self.assertTrue(is_trusted_proxy("10.128.0.1", self.cidrs))

    def test_ip_outside_cidr_is_not_trusted(self):
        self.assertFalse(is_trusted_proxy("192.168.1.1", self.cidrs))

    def test_empty_cidrs_always_false(self):
        self.assertFalse(is_trusted_proxy("10.128.0.1", []))

    def test_invalid_ip_returns_false(self):
        self.assertFalse(is_trusted_proxy("not-an-ip", self.cidrs))

    def test_empty_addr_returns_false(self):
        self.assertFalse(is_trusted_proxy("", self.cidrs))


class TestGetClientIp(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, remote_addr, xff=None, x_real_ip=None):
        req = self.factory.get("/")
        req.META["REMOTE_ADDR"] = remote_addr
        if xff:
            req.META["HTTP_X_FORWARDED_FOR"] = xff
        if x_real_ip:
            req.META["HTTP_X_REAL_IP"] = x_real_ip
        return req

    def test_no_proxy_config_uses_remote_addr(self):
        """Without TRUSTED_PROXY_CIDRS, always use REMOTE_ADDR directly."""
        with self.settings(TRUSTED_PROXY_CIDRS=""):
            req = self._request("1.2.3.4", xff="5.6.7.8")
            self.assertEqual(get_client_ip(req), "1.2.3.4")

    def test_trusted_proxy_reads_xff_leftmost(self):
        """From a trusted proxy, use the leftmost XFF entry (original client)."""
        with self.settings(TRUSTED_PROXY_CIDRS="10.0.0.0/8"):
            req = self._request("10.0.0.1", xff="203.0.113.5, 10.0.0.1")
            self.assertEqual(get_client_ip(req), "203.0.113.5")

    def test_trusted_proxy_single_xff(self):
        with self.settings(TRUSTED_PROXY_CIDRS="10.0.0.0/8"):
            req = self._request("10.0.0.1", xff="203.0.113.5")
            self.assertEqual(get_client_ip(req), "203.0.113.5")

    def test_trusted_proxy_no_xff_falls_back_to_x_real_ip(self):
        with self.settings(TRUSTED_PROXY_CIDRS="10.0.0.0/8"):
            req = self._request("10.0.0.1", x_real_ip="203.0.113.5")
            self.assertEqual(get_client_ip(req), "203.0.113.5")

    def test_trusted_proxy_no_xff_no_real_ip_uses_remote_addr(self):
        with self.settings(TRUSTED_PROXY_CIDRS="10.0.0.0/8"):
            req = self._request("10.0.0.1")
            self.assertEqual(get_client_ip(req), "10.0.0.1")

    def test_untrusted_proxy_xff_is_ignored(self):
        """XFF from an untrusted source must never override REMOTE_ADDR."""
        with self.settings(TRUSTED_PROXY_CIDRS="10.0.0.0/8"):
            req = self._request("1.2.3.4", xff="attacker-ip")
            self.assertEqual(get_client_ip(req), "1.2.3.4")


class TestIPWhitelistMiddleware(TestCase):
    """Integration tests for the middleware using ip_utils."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user("testop", password="pass")

    def test_whitelist_disabled_allows_all(self):
        from apps.core.models import SystemConfiguration

        config = SystemConfiguration.get()
        config.enable_ip_whitelist = False
        config.save()

        self.client.force_login(self.user)
        response = self.client.get("/api/test/")

        # Should not be blocked by middleware.
        # It may return 404 because the URL does not exist, but it must not return 403.
        self.assertNotEqual(response.status_code, 403)

    def test_tables_missing_does_not_crash_startup(self):
        from django.db import OperationalError
        from apps.core.middleware import IPWhitelistMiddleware

        middleware = IPWhitelistMiddleware(get_response=lambda r: None)
        factory = RequestFactory()
        req = factory.get("/api/test/")
        req.META["REMOTE_ADDR"] = "127.0.0.1"

        with patch("apps.core.models.SystemConfiguration.get") as mock_get:
            mock_get.side_effect = OperationalError("table not found")
            result = middleware.process_request(req)

        self.assertIsNone(result)
