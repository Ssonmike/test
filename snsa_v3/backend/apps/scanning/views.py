"""
Endpoints:
  POST /api/hu/lookup/              — HU lookup and session creation
  GET  /api/hu/<session_id>/        — Session detail / recovery
  POST /api/hu/<session_id>/scan/   — Process a barcode scan
  POST /api/hu/<session_id>/complete/ — Confirm and push to SAP
"""
import logging
import time

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import ScanSession
from .serializers import (
    HULookupSerializer,
    ScanInputSerializer,
    ScanSessionSerializer,
    ScanSessionDetailSerializer,
)
from .services.workflow import lookup_hu, process_scan, complete_session
from apps.core.ip_utils import get_client_ip as _get_client_ip

logger = logging.getLogger("apps.scanning")

# Debounce tracking: {(session_id, normalized_input): timestamp}
_recent_scans: dict[tuple, float] = {}
DEBOUNCE_MS = 200


def _error(detail: str, code: str, http_status: int, **extra) -> Response:
    payload = {"detail": detail, "code": code, **extra}
    return Response(payload, status=http_status)


# ─── POST /api/hu/lookup/ ────────────────────────────────────────────────────

@api_view(["POST"])
def hu_lookup(request):
    """Look up an HU, create/recover a session."""
    ser = HULookupSerializer(data=request.data)
    if not ser.is_valid():
        return _error("Invalid input.", "VALIDATION_ERROR", status.HTTP_400_BAD_REQUEST)

    hu_number = ser.validated_data["hu_number"]
    operator = request.user if request.user.is_authenticated else None
    device_ip = _get_client_ip(request)

    result = lookup_hu(hu_number, operator=operator, device_ip=device_ip)

    if not result.success:
        return _error(
            result.error_message,
            result.error_code,
            result.http_status,
        )

    session = result.session
    data = ScanSessionSerializer(session).data
    return Response(data, status=result.http_status)


# ─── GET /api/hu/<session_id>/ ────────────────────────────────────────────────

@api_view(["GET"])
def session_detail(request, session_id):
    """Return full session state for recovery/reload."""
    try:
        session = ScanSession.objects.prefetch_related(
            "content_items__scans", "content_items__sn_profile"
        ).get(pk=session_id)
    except ScanSession.DoesNotExist:
        return _error("Session not found.", "SESSION_NOT_FOUND", status.HTTP_404_NOT_FOUND)

    return Response(ScanSessionDetailSerializer(session).data)


# ─── POST /api/hu/<session_id>/scan/ ─────────────────────────────────────────

@api_view(["POST"])
def scan_endpoint(request, session_id):
    """Process a barcode scan within an active session."""
    try:
        session = ScanSession.objects.prefetch_related(
            "content_items__scans", "content_items__sn_profile"
        ).get(pk=session_id)
    except ScanSession.DoesNotExist:
        return _error("Session not found.", "SESSION_NOT_FOUND", status.HTTP_404_NOT_FOUND)

    ser = ScanInputSerializer(data=request.data)
    if not ser.is_valid():
        return _error("Invalid scan data.", "VALIDATION_ERROR", status.HTTP_400_BAD_REQUEST)

    scan_input = ser.validated_data["scan_input"]
    manual_item_id = ser.validated_data.get("manual_item_id")
    device_ip = _get_client_ip(request)
    operator = request.user if request.user.is_authenticated else None

    # Debounce duplicate rapid inputs
    debounce_key = (session_id, scan_input.strip())
    now = time.monotonic() * 1000
    last_time = _recent_scans.get(debounce_key, 0)
    if now - last_time < DEBOUNCE_MS:
        return _error(
            "Duplicate scan detected (debounce).",
            "DEBOUNCE",
            status.HTTP_429_TOO_MANY_REQUESTS,
        )
    _recent_scans[debounce_key] = now

    # Cleanup old debounce entries (keep memory bounded)
    if len(_recent_scans) > 10000:
        _recent_scans.clear()

    result = process_scan(
        session, scan_input,
        manual_item_id=manual_item_id,
        device_ip=device_ip,
        operator=operator,
    )

    # Reload session for serialization
    session.refresh_from_db()

    if result.accepted:
        session_data = ScanSessionSerializer(
            ScanSession.objects.prefetch_related(
                "content_items__scans", "content_items__sn_profile"
            ).get(pk=session_id)
        ).data
        return Response({
            "session": session_data,
            "scan_result": {
                "accepted": True,
                "barcode_type": result.barcode_type,
                "matched_item_id": result.matched_item_id,
                "matched_item_label": result.matched_item_label,
                "serial_number": result.serial_number,
                "remaining_for_item": result.remaining_for_item,
                "session_ready_to_complete": result.session_ready_to_complete,
            },
        })

    # EAN scan that identified item but needs serial next
    if result.awaiting_serial:
        session_data = ScanSessionSerializer(
            ScanSession.objects.prefetch_related(
                "content_items__scans", "content_items__sn_profile"
            ).get(pk=session_id)
        ).data
        return Response({
            "session": session_data,
            "scan_result": {
                "accepted": False,
                "awaiting_serial": True,
                "awaiting_serial_for_item": result.awaiting_serial_for_item,
                "matched_item_id": result.matched_item_id,
                "matched_item_label": result.matched_item_label,
                "remaining_for_item": result.remaining_for_item,
                "barcode_type": result.barcode_type,
            },
        })

    # Error
    error_payload = {
        "code": result.error_code,
        "message": result.error_message,
        "retryable": result.retryable,
        "session_status": result.session_status,
    }
    if result.ambiguous_items:
        error_payload["ambiguous_items"] = result.ambiguous_items

    http_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    if result.error_code == "SESSION_INVALID_STATE":
        http_code = status.HTTP_409_CONFLICT
    elif result.error_code == "SCAN_PARSE_ERROR":
        http_code = status.HTTP_400_BAD_REQUEST

    return Response(error_payload, status=http_code)


# ─── POST /api/hu/<session_id>/complete/ ──────────────────────────────────────

@api_view(["POST"])
def complete_endpoint(request, session_id):
    """Explicitly confirm and push session to SAP."""
    try:
        session = ScanSession.objects.get(pk=session_id)
    except ScanSession.DoesNotExist:
        return _error("Session not found.", "SESSION_NOT_FOUND", status.HTTP_404_NOT_FOUND)

    if session.status == ScanSession.STATUS_COMPLETED:
        return Response(ScanSessionSerializer(session).data)

    if session.status not in session.COMPLETABLE_STATUSES:
        return _error(
            f"Cannot complete session in state '{session.status}'.",
            "SESSION_INVALID_STATE",
            status.HTTP_409_CONFLICT,
        )

    device_ip = _get_client_ip(request)
    operator = request.user if request.user.is_authenticated else None

    success, sap_ref, error_msg = complete_session(
        session, device_ip=device_ip, operator=operator
    )

    session.refresh_from_db()
    session_data = ScanSessionSerializer(session).data

    if success:
        return Response({
            "session": session_data,
            "sap_document_ref": sap_ref,
        })
    else:
        return Response({
            "session": session_data,
            "code": "SAP_PUSH_FAILED",
            "message": error_msg,
        }, status=status.HTTP_502_BAD_GATEWAY)


# ─── GET /api/scanning/sessions/ (supervisor/debug) ──────────────────────────

@api_view(["GET"])
def list_sessions(request):
    sessions = ScanSession.objects.prefetch_related(
        "content_items"
    ).order_by("-created_at")[:50]
    return Response(ScanSessionSerializer(sessions, many=True).data)
