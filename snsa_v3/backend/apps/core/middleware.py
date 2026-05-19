import logging

from django.db import OperationalError, ProgrammingError
from django.http import HttpResponseForbidden, JsonResponse
from django.utils.deprecation import MiddlewareMixin

from apps.core.ip_utils import get_client_ip

logger = logging.getLogger("apps.core")


HEALTH_PATHS = {
    "/api/health/live/",
    "/api/health/ready/",
}


class IPWhitelistMiddleware(MiddlewareMixin):
    """
    Blocks requests whose resolved client IP is not present in AllowedIP when
    SystemConfiguration.enable_ip_whitelist is enabled.

    Proxy security:
    - X-Forwarded-For is only trusted when REMOTE_ADDR belongs to a configured
      trusted proxy CIDR in TRUSTED_PROXY_CIDRS.
    - The actual IP resolution logic lives in apps.core.ip_utils.

    OpenShift compatibility:
    - Health endpoints are always allowed so readiness/liveness probes cannot be
      blocked by the application-level whitelist.
    - If DB tables do not exist yet during first migration/startup, the middleware
      does not block requests.
    """

    def process_request(self, request):
        if request.path in HEALTH_PATHS:
            return None

        try:
            from .models import AllowedIP, SystemConfiguration

            config = SystemConfiguration.get()
            if not config.enable_ip_whitelist:
                return None

            client_ip = get_client_ip(request)
            if not client_ip:
                logger.warning(
                    "Unable to determine client IP. path=%s method=%s",
                    request.path,
                    request.method,
                )
                return self._deny(request, "Access denied: unable to determine client IP.")

            is_allowed = AllowedIP.objects.filter(
                ip_address=client_ip,
                is_active=True,
            ).exists()

            if is_allowed:
                return None

            logger.warning(
                "Access denied by IP whitelist. ip=%s path=%s method=%s",
                client_ip,
                request.path,
                request.method,
            )
            return self._deny(request, f"Access denied for IP {client_ip}.")

        except (OperationalError, ProgrammingError):
            # During first migration/startup, the DB tables may not exist yet.
            return None

    @staticmethod
    def _deny(request, detail):
        if request.path.startswith("/api/"):
            return JsonResponse({"detail": detail}, status=403)

        return HttpResponseForbidden(detail)
