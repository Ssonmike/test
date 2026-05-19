"""
HTML views for warehouse operator frontend.

Zebra-friendly, HTMX-powered, keyboard-wedge-scanner optimized.
No auto-push to SAP — explicit operator confirmation required.
"""
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse

from .models import ScanSession
from .services.workflow import lookup_hu, process_scan, complete_session
from apps.core.ip_utils import get_client_ip as _get_client_ip

logger = logging.getLogger("apps.scanning")


# ─── HU Lookup Page ──────────────────────────────────────────────────────────

@login_required
def hu_lookup_page(request):
    """GET: show HU scan form. POST: create/recover session and redirect."""
    if request.method == "GET":
        return render(request, "scanning/hu_lookup.html")

    hu_number = request.POST.get("hu_number", "").strip()
    if not hu_number:
        return render(request, "scanning/_scan_feedback.html", {
            "error": "Scan or enter HU number.",
            "code": "VALIDATION_ERROR",
        })

    device_ip = _get_client_ip(request)
    result = lookup_hu(hu_number, operator=request.user, device_ip=device_ip)

    if not result.success:
        return render(request, "scanning/_scan_feedback.html", {
            "error": result.error_message,
            "code": result.error_code,
        })

    session = result.session

    # No serialization required
    if session.status == ScanSession.STATUS_NO_SERIALIZATION:
        response = HttpResponse()
        response["HX-Redirect"] = reverse("session-no-serialization-page", args=[session.id])
        return response

    # Redirect to scan page — the scan page itself handles further state routing
    response = HttpResponse()
    response["HX-Redirect"] = reverse("session-scan-page", args=[session.id])
    return response


# ─── Session Scan Page ────────────────────────────────────────────────────────

@login_required
def session_scan_page(request, session_id):
    """
    GET: Render full session scan page.
    POST: Process scan via HTMX, return updated content.

    On GET, the session state is checked first so that an operator who
    reconnects after a disconnection (or refreshes the page) is always
    routed to the correct screen — even if the session already moved
    past the scanning stage while they were away.
    """
    session = get_object_or_404(
        ScanSession.objects.prefetch_related("content_items__scans", "content_items__sn_profile"),
        pk=session_id,
    )

    if request.method == "GET":
        # ── Reconnection / state recovery ────────────────────────────
        # If the session is no longer in a scannable state, redirect to
        # the appropriate page instead of showing a frozen scan screen.
        if session.status == ScanSession.STATUS_READY_TO_COMPLETE:
            logger.info(
                "Session %s is ready_to_complete — redirecting to confirm page",
                session.id,
            )
            return redirect(reverse("session-confirm-page", args=[session.id]))

        if session.status == ScanSession.STATUS_SAP_PUSH_FAILED:
            logger.info(
                "Session %s is sap_push_failed — redirecting to retry page",
                session.id,
            )
            return redirect(reverse("session-retry-page", args=[session.id]))

        if session.status == ScanSession.STATUS_COMPLETED:
            logger.info(
                "Session %s is already completed — redirecting to complete page",
                session.id,
            )
            return redirect(reverse("session-complete-page", args=[session.id]))

        if session.status == ScanSession.STATUS_NO_SERIALIZATION:
            return redirect(reverse("session-no-serialization-page", args=[session.id]))
        # ── end state recovery ────────────────────────────────────────

        return _render_session_page(request, session)

    # POST — process scan
    scan_input = request.POST.get("scan_input", "").strip()
    manual_item_id = request.POST.get("manual_item_id")
    if manual_item_id:
        try:
            manual_item_id = int(manual_item_id)
        except (ValueError, TypeError):
            manual_item_id = None

    device_ip = _get_client_ip(request)

    if not scan_input:
        return _render_scan_area(request, session, scan_error="Scan a barcode.")

    result = process_scan(
        session, scan_input,
        manual_item_id=manual_item_id,
        device_ip=device_ip,
        operator=request.user,
    )

    # Reload session to get updated status after processing
    session = ScanSession.objects.prefetch_related(
        "content_items__scans", "content_items__sn_profile"
    ).get(pk=session_id)

    if result.accepted:
        # Check if ready to complete → redirect to confirmation
        if session.status == ScanSession.STATUS_READY_TO_COMPLETE:
            response = HttpResponse()
            response["HX-Redirect"] = reverse("session-confirm-page", args=[session.id])
            return response

        return _render_scan_area(
            request, session,
            scan_ok=f"✓ {result.serial_number} — {result.matched_item_label}",
        )

    if result.awaiting_serial:
        return _render_scan_area(
            request, session,
            scan_info=f"Item identified: {result.awaiting_serial_for_item}. Now scan serial number.",
        )

    return _render_scan_area(
        request, session,
        scan_error=result.error_message,
        error_code=result.error_code,
    )


# ─── Confirmation Page ────────────────────────────────────────────────────────

@login_required
def session_confirm_page(request, session_id):
    """Show confirmation screen when all serials are scanned."""
    session = get_object_or_404(
        ScanSession.objects.prefetch_related("content_items__scans"),
        pk=session_id,
    )

    if request.method == "GET":
        return render(request, "scanning/session_confirm.html", {
            "session": session,
            "items": session.content_items.filter(is_serialised=True),
        })

    # POST — trigger SAP push
    device_ip = _get_client_ip(request)
    success, sap_ref, error_msg = complete_session(
        session, device_ip=device_ip, operator=request.user
    )

    session.refresh_from_db()

    if success:
        response = HttpResponse()
        response["HX-Redirect"] = reverse("session-complete-page", args=[session.id])
        return response

    return render(request, "scanning/_push_error.html", {
        "session": session,
        "error": error_msg,
    })


# ─── Completion Page ──────────────────────────────────────────────────────────

@login_required
def session_complete_page(request, session_id):
    session = get_object_or_404(ScanSession, pk=session_id)
    return render(request, "scanning/session_complete.html", {"session": session})


# ─── No Serialization Page ───────────────────────────────────────────────────

@login_required
def session_no_serialization_page(request, session_id):
    session = get_object_or_404(ScanSession, pk=session_id)
    return render(request, "scanning/session_no_serialization.html", {"session": session})


# ─── Push Failed / Retry ─────────────────────────────────────────────────────

@login_required
def session_retry_page(request, session_id):
    session = get_object_or_404(ScanSession, pk=session_id)
    if session.status != ScanSession.STATUS_SAP_PUSH_FAILED:
        return redirect("session-scan-page", session_id=session_id)

    if request.method == "POST":
        device_ip = _get_client_ip(request)
        success, sap_ref, error_msg = complete_session(
            session, device_ip=device_ip, operator=request.user
        )
        session.refresh_from_db()
        if success:
            response = HttpResponse()
            response["HX-Redirect"] = reverse("session-complete-page", args=[session.id])
            return response
        return render(request, "scanning/_push_error.html", {
            "session": session,
            "error": error_msg,
        })

    return render(request, "scanning/session_push_failed.html", {"session": session})


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _render_session_page(request, session):
    """Render the full session scan page."""
    items = session.content_items.filter(is_serialised=True)
    total_exp = sum(i.expected_qty for i in items)
    total_scn = sum(i.scanned_qty for i in items)
    progress_pct = (total_scn / total_exp * 100) if total_exp > 0 else 0

    # Pending item context
    pending_item = None
    if session.pending_item_id:
        pending_item = session.content_items.filter(pk=session.pending_item_id).first()

    return render(request, "scanning/session_detail.html", {
        "session": session,
        "items": items,
        "progress_pct": progress_pct,
        "total_expected": total_exp,
        "total_scanned": total_scn,
        "pending_item": pending_item,
    })


def _render_scan_area(request, session, scan_ok="", scan_error="", scan_info="", error_code=""):
    """Render the HTMX-swappable scan area partial."""
    items = session.content_items.filter(is_serialised=True)
    total_exp = sum(i.expected_qty for i in items)
    total_scn = sum(i.scanned_qty for i in items)
    progress_pct = (total_scn / total_exp * 100) if total_exp > 0 else 0

    pending_item = None
    if session.pending_item_id:
        pending_item = session.content_items.filter(pk=session.pending_item_id).first()

    return render(request, "scanning/_scan_area.html", {
        "session": session,
        "items": items,
        "progress_pct": progress_pct,
        "total_expected": total_exp,
        "total_scanned": total_scn,
        "pending_item": pending_item,
        "scan_ok": scan_ok,
        "scan_error": scan_error,
        "scan_info": scan_info,
        "error_code": error_code,
    })
