"""
Shared IP resolution utility.

Used by:
  - apps.core.middleware.IPWhitelistMiddleware
  - apps.scanning.views (API)
  - apps.scanning.views_html (HTML)

X-Forwarded-For is only trusted when the originating REMOTE_ADDR
falls within a configured TRUSTED_PROXY_CIDRS range. Otherwise
REMOTE_ADDR is used directly to prevent client IP spoofing.
"""

import ipaddress
import logging

from django.conf import settings

logger = logging.getLogger("apps.core")


def parse_trusted_cidrs() -> list:
    """
    Load TRUSTED_PROXY_CIDRS from settings (space or comma-separated CIDRs).
    Returns a list of ip_network objects. Invalid entries are skipped with a warning.
    """
    raw = getattr(settings, "TRUSTED_PROXY_CIDRS", "").strip()
    if not raw:
        return []

    networks = []
    for part in raw.replace(",", " ").split():
        part = part.strip()
        if not part:
            continue
        try:
            networks.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            logger.warning("TRUSTED_PROXY_CIDRS: invalid CIDR ignored: %r", part)
    return networks


def is_trusted_proxy(remote_addr: str, trusted_cidrs: list) -> bool:
    """Return True if remote_addr is within any of the trusted CIDRs."""
    if not trusted_cidrs or not remote_addr:
        return False
    try:
        addr = ipaddress.ip_address(remote_addr)
    except ValueError:
        return False
    return any(addr in cidr for cidr in trusted_cidrs)


def get_client_ip(request) -> str:
    """
    Resolve the real client IP from a Django request.

    Trust chain:
      1. If REMOTE_ADDR is a known trusted proxy → read X-Forwarded-For (leftmost entry).
      2. If REMOTE_ADDR is a known trusted proxy but no XFF → try X-Real-IP.
      3. Otherwise → use REMOTE_ADDR directly.

    With no TRUSTED_PROXY_CIDRS configured (local dev), always uses REMOTE_ADDR.
    """
    remote_addr = request.META.get("REMOTE_ADDR", "").strip()
    trusted_cidrs = parse_trusted_cidrs()

    if is_trusted_proxy(remote_addr, trusted_cidrs):
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "").strip()
        if xff:
            return xff.split(",")[0].strip()

        x_real_ip = request.META.get("HTTP_X_REAL_IP", "").strip()
        if x_real_ip:
            return x_real_ip

    return remote_addr
