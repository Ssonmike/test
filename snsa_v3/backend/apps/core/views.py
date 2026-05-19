from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny


@api_view(["GET"])
@permission_classes([AllowAny])
def health_live(request):
    """
    Liveness probe — Django process is alive.
    OpenShift: livenessProbe → /api/health/live/
    """
    return JsonResponse({"status": "ok", "check": "live", "app": "SNSA"})


@api_view(["GET"])
@permission_classes([AllowAny])
def health_ready(request):
    """
    Readiness probe — app is ready to serve traffic (DB reachable).
    OpenShift: readinessProbe → /api/health/ready/
    Returns 503 if the DB is unreachable so the pod is removed from rotation.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return JsonResponse({"status": "ok", "check": "ready", "db": "ok", "app": "SNSA"})
    except (OperationalError, ProgrammingError, Exception) as exc:
        return JsonResponse(
            {
                "status": "error",
                "check": "ready",
                "db": "unavailable",
                "detail": str(exc),
                "app": "SNSA",
            },
            status=503,
        )
