# Workflow orchestrator for SNSA scan sessions.

# Coordinates:
# - HU lookup and session creation
# - Scan processing (GS1, EAN, serial)
# - Single SKU vs Multi SKU flow logic
# - State transitions
# - Completion and SAP push

import logging
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.acf.client import ACFClient, ACFError
from apps.scanning.models import (
    HUContentItem, ScanSession, SerialNumberScan, ScanLog, SNProfile,
)
from .barcodes import detect_and_parse, BarcodeParseResult
from .matching import match_item
from .validation import validate_scan

logger = logging.getLogger("apps.scanning")

# Pending item context timeout in seconds
PENDING_ITEM_TIMEOUT_SECONDS = 120


# ─── Result dataclasses ──────────────────────────────────────────────────────

@dataclass
class LookupResult:
    success: bool = False
    session: ScanSession | None = None
    error_code: str = ""
    error_message: str = ""
    http_status: int = 200


@dataclass
class ScanResult:
    accepted: bool = False
    barcode_type: str = "unknown"
    matched_item_id: int | None = None
    matched_item_label: str = ""
    serial_number: str = ""
    remaining_for_item: int | None = None
    session_ready_to_complete: bool = False
    # For EAN-first flow: item identified but serial still needed
    awaiting_serial: bool = False
    awaiting_serial_for_item: str = ""
    # Error info
    error_code: str = ""
    error_message: str = ""
    retryable: bool = True
    session_status: str = ""
    # Ambiguity
    ambiguous_items: list = field(default_factory=list)


# ─── HU Lookup & Session Creation ────────────────────────────────────────────

def lookup_hu(
    hu_number: str,
    operator=None,
    device_ip: str = "",
) -> LookupResult:
    hu_number = hu_number.strip().upper()

    if not hu_number:
        return LookupResult(
            error_code="VALIDATION_ERROR",
            error_message="HU number is required.",
            http_status=400,
        )

    # Check for existing active session
    active = ScanSession.objects.filter(
        hu_number=hu_number,
        status__in=[
            ScanSession.STATUS_READY_TO_SCAN,
            ScanSession.STATUS_SCAN_IN_PROGRESS,
            ScanSession.STATUS_READY_TO_COMPLETE,
            ScanSession.STATUS_SAP_PUSH_FAILED,
        ],
    ).first()

    if active:
        return LookupResult(
            success=True,
            session=active,
            http_status=200,
        )

    # Create session
    session = ScanSession.objects.create(
        hu_number=hu_number,
        status=ScanSession.STATUS_PENDING_LOOKUP,
        operator=operator,
        device_ip=device_ip or None,
    )

    _log_event(session, "session_created", {"hu_number": hu_number}, device_ip, operator)

    # Call ACF
    client = ACFClient(session_id=session.id)
    try:
        hu_data = client.get_hu(hu_number)
    except ACFError as e:
        session.status = ScanSession.STATUS_ERROR_LOOKUP_FAILED
        session.failure_reason = str(e)
        session.save(update_fields=["status", "failure_reason"])
        _log_event(session, "hu_lookup_failed", {"error": str(e)}, device_ip, operator)

        error_code = "HU_NOT_FOUND" if "not found" in str(e).lower() or "404" in str(e) else "ACF_LOOKUP_FAILED"
        http_status = 404 if error_code == "HU_NOT_FOUND" else 502
        return LookupResult(
            error_code=error_code,
            error_message=str(e),
            http_status=http_status,
        )

    # Load content items
    with transaction.atomic():
        serialised_count = 0
        for idx, item in enumerate(hu_data.items):
            is_ser = bool(item.sn_profile and item.is_serialised)

            # Try to link SNProfile
            sn_profile_obj = None
            if item.sn_profile:
                sn_profile_obj = SNProfile.objects.filter(
                    code=item.sn_profile, is_active=True
                ).first()

            HUContentItem.objects.create(
                session=session,
                material_number=item.material,
                description=item.description,
                expected_qty=item.expected_qty,
                is_serialised=is_ser,
                sn_profile_code=item.sn_profile or "",
                sn_profile=sn_profile_obj,
                batch=item.batch or "",
                delivery_ref=item.delivery_ref or "",
                manufacturing_part_number=item.manufacturing_part_number or "",
                ean_code=item.ean_code or "",
                uom=item.uom or "EA",
                sort_order=idx,
            )
            if is_ser:
                serialised_count += 1

        # Determine flow type and status
        if serialised_count == 0:
            session.flow_type = ScanSession.FLOW_NO_SERIALIZATION
            session.status = ScanSession.STATUS_NO_SERIALIZATION
        elif serialised_count == 1:
            session.flow_type = ScanSession.FLOW_SINGLE_SKU
            session.status = ScanSession.STATUS_READY_TO_SCAN
        else:
            session.flow_type = ScanSession.FLOW_MULTI_SKU
            session.status = ScanSession.STATUS_READY_TO_SCAN

        session.save(update_fields=["flow_type", "status"])

    _log_event(session, "hu_lookup_ok", {
        "items": len(hu_data.items),
        "serialised": serialised_count,
        "flow_type": session.flow_type,
    }, device_ip, operator)

    return LookupResult(success=True, session=session, http_status=201)


# ─── Scan Processing ─────────────────────────────────────────────────────────

def process_scan(
    session: ScanSession,
    scan_input: str,
    manual_item_id: int | None = None,
    device_ip: str = "",
    operator=None,
) -> ScanResult:
    if not scan_input or not scan_input.strip():
        return ScanResult(
            error_code="SCAN_PARSE_ERROR",
            error_message="Empty scan input.",
            retryable=True,
            session_status=session.status,
        )

    # State guard
    if session.status not in session.SCANNABLE_STATUSES:
        return ScanResult(
            error_code="SESSION_INVALID_STATE",
            error_message=f"Session is in state '{session.status}' and cannot accept scans.",
            retryable=False,
            session_status=session.status,
        )

    # Parse barcode
    parsed = detect_and_parse(scan_input)

    # ── GS1 DataMatrix ────────────────────────────────────────────────
    if parsed.barcode_type == "gs1":
        return _handle_gs1_scan(session, parsed, manual_item_id, device_ip, operator)

    # ── EAN-13 ────────────────────────────────────────────────────────
    if parsed.barcode_type == "ean":
        return _handle_ean_scan(session, parsed, device_ip, operator)

    # ── Serial Number ─────────────────────────────────────────────────
    if parsed.barcode_type == "serial":
        return _handle_serial_scan(session, parsed, manual_item_id, device_ip, operator)

    # ── Unknown ───────────────────────────────────────────────────────
    _record_invalid_scan(session, parsed, "", "SCAN_PARSE_ERROR",
                         "Unrecognized barcode type", device_ip)
    return ScanResult(
        error_code="SCAN_PARSE_ERROR",
        error_message="Cannot identify barcode type for input.",
        retryable=True,
        session_status=session.status,
    )


def _handle_gs1_scan(
    session: ScanSession,
    parsed: BarcodeParseResult,
    manual_item_id: int | None,
    device_ip: str,
    operator,
) -> ScanResult:
    """Handle GS1 DataMatrix scan: item + serial in one scan."""
    serial = parsed.serial_number
    mfr_part = parsed.manufacturing_part_number

    if not serial:
        _record_invalid_scan(session, parsed, "", "SCAN_PARSE_ERROR",
                             "GS1 barcode has no serial number (AI 21)", device_ip)
        return ScanResult(
            error_code="SCAN_PARSE_ERROR",
            error_message="GS1 barcode does not contain a serial number.",
            barcode_type="gs1",
            retryable=True,
            session_status=session.status,
        )

    # Match item
    match = match_item(
        session,
        manufacturing_part=mfr_part,
        serial=serial,
        manual_item_id=manual_item_id,
    )

    if not match.matched:
        _record_invalid_scan(session, parsed, serial, match.error_code,
                             match.error_message, device_ip)
        result = ScanResult(
            error_code=match.error_code,
            error_message=match.error_message,
            barcode_type="gs1",
            session_status=session.status,
        )
        if match.error_code == "SN_AMBIGUOUS":
            result.ambiguous_items = [
                {"id": i.id, "material": i.material_number, "description": i.description}
                for i in match.ambiguous_items
            ]
        return result

    # Validate
    err = validate_scan(session, match.item, serial)
    if err:
        _record_invalid_scan(session, parsed, serial, err.code, err.message, device_ip)
        return ScanResult(
            error_code=err.code,
            error_message=err.message,
            barcode_type="gs1",
            retryable=err.retryable,
            session_status=session.status,
        )

    # Record valid scan
    return _record_valid_scan(
        session, parsed, match.item, serial, "gs1", device_ip, operator
    )


def _handle_ean_scan(
    session: ScanSession,
    parsed: BarcodeParseResult,
    device_ip: str,
    operator,
) -> ScanResult:
    ean = parsed.ean_code

    match = match_item(session, ean_code=ean)

    if not match.matched:
        if match.error_code == "ITEM_NOT_ON_HU":
            logger.debug(
                "EAN '%s' not found on session %s — retrying as serial number",
                ean, session.id,
            )
            parsed.barcode_type = "serial"
            parsed.serial_number = ean
            parsed.ean_code = ""
            return _handle_serial_scan(session, parsed, None, device_ip, operator)
        # ── end fallback ──────────────────────────────────────────────

        _record_invalid_scan(session, parsed, "", match.error_code,
                             match.error_message, device_ip)
        return ScanResult(
            error_code=match.error_code,
            error_message=match.error_message,
            barcode_type="ean",
            session_status=session.status,
        )

    item = match.item
    if item.is_fully_scanned:
        _record_invalid_scan(session, parsed, "", "SN_QTY_EXCEEDED",
                             f"Item '{item.material_number}' already fully scanned", device_ip)
        return ScanResult(
            error_code="SN_QTY_EXCEEDED",
            error_message=f"Item '{item.material_number}' already fully scanned.",
            barcode_type="ean",
            session_status=session.status,
        )

    # Set pending item context — next scan should be a serial
    session.set_pending_item(item.id)

    _log_event(session, "status_change", {
        "action": "pending_item_set",
        "item_id": item.id,
        "material": item.material_number,
    }, device_ip, operator)

    return ScanResult(
        accepted=False,  # Not a complete scan yet
        barcode_type="ean",
        matched_item_id=item.id,
        matched_item_label=f"{item.material_number} — {item.description}",
        awaiting_serial=True,
        awaiting_serial_for_item=item.material_number,
        remaining_for_item=item.remaining_qty,
        session_status=session.status,
    )


def _handle_serial_scan(
    session: ScanSession,
    parsed: BarcodeParseResult,
    manual_item_id: int | None,
    device_ip: str,
    operator,
) -> ScanResult:
    """
    Handle serial number scan.
    Uses pending item context if available, otherwise tries profile matching.
    """
    serial = parsed.serial_number

    # Check pending item context (EAN-first flow)
    pending_id = _get_valid_pending_item(session)

    match = match_item(
        session,
        serial=serial,
        manual_item_id=manual_item_id,
        pending_item_id=pending_id,
    )

    if not match.matched:
        _record_invalid_scan(session, parsed, serial, match.error_code,
                             match.error_message, device_ip)
        result = ScanResult(
            error_code=match.error_code,
            error_message=match.error_message,
            barcode_type="serial",
            session_status=session.status,
        )
        if match.error_code == "SN_AMBIGUOUS":
            result.ambiguous_items = [
                {"id": i.id, "material": i.material_number, "description": i.description}
                for i in match.ambiguous_items
            ]
        return result

    # Validate
    err = validate_scan(session, match.item, serial)
    if err:
        _record_invalid_scan(session, parsed, serial, err.code, err.message, device_ip)
        return ScanResult(
            error_code=err.code,
            error_message=err.message,
            barcode_type="serial",
            retryable=err.retryable,
            session_status=session.status,
        )
    matched_by = match.matched_by
    if session.flow_type == ScanSession.FLOW_MULTI_SKU:
        session.clear_pending_item()

    return _record_valid_scan(
        session, parsed, match.item, serial, matched_by, device_ip, operator
    )


# ─── Completion ──────────────────────────────────────────────────────────────

def complete_session(
    session: ScanSession,
    device_ip: str = "",
    operator=None,
) -> tuple[bool, str, str]:
    if session.status == ScanSession.STATUS_COMPLETED:
        return True, session.sap_document_ref, ""

    if session.status not in session.COMPLETABLE_STATUSES:
        return False, "", f"Cannot complete session in state '{session.status}'."

    # Build payload
    payload = _build_push_payload(session)

    # Mark push in progress
    session.status = ScanSession.STATUS_SAP_PUSH_IN_PROGRESS
    session.sap_push_attempts = F("sap_push_attempts") + 1
    session.save(update_fields=["status", "sap_push_attempts"])
    session.refresh_from_db()

    _log_event(session, "sap_push_started", {
        "attempt": session.sap_push_attempts,
        "scans_count": len(payload.get("items", [])),
    }, device_ip, operator)

    # Push to SAP via ACF
    client = ACFClient(session_id=session.id)
    try:
        result = client.push_serials(payload)
        session.status = ScanSession.STATUS_COMPLETED
        session.sap_document_ref = result.get("sap_document_ref", "")
        session.completed_at = timezone.now()
        session.save(update_fields=["status", "sap_document_ref", "completed_at"])

        _log_event(session, "sap_push_ok", {
            "sap_document_ref": session.sap_document_ref,
        }, device_ip, operator)

        return True, session.sap_document_ref, ""

    except ACFError as e:
        session.status = ScanSession.STATUS_SAP_PUSH_FAILED
        session.failure_reason = str(e)
        session.save(update_fields=["status", "failure_reason"])

        _log_event(session, "sap_push_failed", {"error": str(e)}, device_ip, operator)

        return False, "", str(e)


# ─── Internal helpers ────────────────────────────────────────────────────────

def _get_valid_pending_item(session: ScanSession) -> int | None:
    """Get pending item ID if context is still valid (not expired)."""
    if not session.pending_item_id or not session.pending_item_set_at:
        return None

    elapsed = (timezone.now() - session.pending_item_set_at).total_seconds()
    if elapsed > PENDING_ITEM_TIMEOUT_SECONDS:
        session.clear_pending_item()
        return None

    return session.pending_item_id


def _record_valid_scan(
    session: ScanSession,
    parsed: BarcodeParseResult,
    item: HUContentItem,
    serial: str,
    matched_by: str,
    device_ip: str,
    operator,
) -> ScanResult:
    """Record a validated scan, update counters, check completion."""
    with transaction.atomic():
        # Lock the item row for counter update
        locked_item = HUContentItem.objects.select_for_update().get(pk=item.id)

        # Double-check qty under lock
        if locked_item.scanned_qty >= locked_item.expected_qty:
            return ScanResult(
                error_code="SN_QTY_EXCEEDED",
                error_message=f"Item '{item.material_number}' was completed by another scan.",
                barcode_type=parsed.barcode_type,
                session_status=session.status,
            )

        # Check duplicate under lock
        dup = SerialNumberScan.objects.filter(
            session=session, scanned_serial=serial, is_valid=True,
        ).exists()
        if dup:
            return ScanResult(
                error_code="SN_DUPLICATE_LOCAL",
                error_message=f"Serial '{serial}' already scanned in this session.",
                barcode_type=parsed.barcode_type,
                session_status=session.status,
            )

        # Create scan record
        SerialNumberScan.objects.create(
            session=session,
            content_item=locked_item,
            raw_input=parsed.raw_input,
            normalized_input=parsed.normalized_input,
            barcode_type=parsed.barcode_type,
            scanned_ean=parsed.ean_code,
            scanned_manufacturing_part=parsed.manufacturing_part_number,
            scanned_serial=serial,
            is_valid=True,
            matched_by=matched_by,
            device_ip=device_ip or None,
        )

        # Update item counter atomically
        locked_item.scanned_qty = F("scanned_qty") + 1
        locked_item.last_scanned_at = timezone.now()
        locked_item.save(update_fields=["scanned_qty", "last_scanned_at"])

        # Update session display fields
        session.last_scanned_item_display = f"{item.material_number}"
        session.last_scanned_serial_display = serial

        # Transition to scan_in_progress if first scan
        if session.status == ScanSession.STATUS_READY_TO_SCAN:
            session.status = ScanSession.STATUS_SCAN_IN_PROGRESS

        session.save(update_fields=[
            "status", "last_scanned_item_display", "last_scanned_serial_display",
        ])

    # Refresh to get actual counter values
    locked_item.refresh_from_db()
    session.refresh_from_db()

    _log_event(session, "scan_accepted", {
        "serial": serial,
        "item": item.material_number,
        "matched_by": matched_by,
        "barcode_type": parsed.barcode_type,
        "scanned_qty": locked_item.scanned_qty,
        "expected_qty": locked_item.expected_qty,
    }, device_ip, operator)

    # Check if item just became fully scanned
    if locked_item.is_fully_scanned:
        _log_event(session, "item_completed", {
            "item": item.material_number,
        }, device_ip, operator)

    # Check if all items are now complete → ready_to_complete
    ready = session.is_all_scanned
    if ready and session.status != ScanSession.STATUS_READY_TO_COMPLETE:
        session.status = ScanSession.STATUS_READY_TO_COMPLETE
        session.save(update_fields=["status"])
        _log_event(session, "session_ready", {}, device_ip, operator)

    return ScanResult(
        accepted=True,
        barcode_type=parsed.barcode_type,
        matched_item_id=locked_item.id,
        matched_item_label=f"{item.material_number} — {item.description}",
        serial_number=serial,
        remaining_for_item=locked_item.remaining_qty,
        session_ready_to_complete=ready,
        session_status=session.status,
    )


def _record_invalid_scan(
    session: ScanSession,
    parsed: BarcodeParseResult,
    serial: str,
    rejection_code: str,
    rejection_reason: str,
    device_ip: str,
):
    """Record an invalid scan attempt for audit purposes."""
    try:
        SerialNumberScan.objects.create(
            session=session,
            raw_input=parsed.raw_input,
            normalized_input=parsed.normalized_input,
            barcode_type=parsed.barcode_type,
            scanned_ean=parsed.ean_code,
            scanned_manufacturing_part=parsed.manufacturing_part_number,
            scanned_serial=serial,
            is_valid=False,
            rejection_code=rejection_code,
            rejection_reason=rejection_reason,
            device_ip=device_ip or None,
        )
    except Exception as e:
        logger.warning("Failed to record invalid scan: %s", e)

    _log_event(session, "scan_rejected", {
        "serial": serial,
        "code": rejection_code,
        "reason": rejection_reason,
    }, device_ip)


def _build_push_payload(session: ScanSession) -> dict:
    items = []
    for content_item in session.content_items.filter(is_serialised=True):
        serial_numbers = list(
            content_item.scans.filter(is_valid=True).values_list(
                "scanned_serial", flat=True
            )
        )
        if not serial_numbers:
            continue
        items.append({
            "material": content_item.material_number,
            "manufacturingPartNumber": content_item.manufacturing_part_number,
            "eanCode": content_item.ean_code,
            "batch": content_item.batch,
            "uom": content_item.uom,
            "serialNumberProfile": content_item.sn_profile_code,
            "serialNumbers": serial_numbers,
        })

    return {
        "huNumber": session.hu_number,
        "sessionId": str(session.id),
        "items": items,
    }


def _log_event(
    session: ScanSession,
    event_type: str,
    detail: dict,
    device_ip: str = "",
    operator=None,
):
    """Write an event to the ScanLog."""
    try:
        ScanLog.objects.create(
            session=session,
            event_type=event_type,
            detail=detail,
            device_ip=device_ip or None,
            operator_id=operator.id if operator and hasattr(operator, "id") else None,
        )
    except Exception as e:
        logger.warning("ScanLog write failed: %s", e)
