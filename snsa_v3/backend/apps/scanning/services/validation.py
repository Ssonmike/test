import logging

from apps.scanning.models import HUContentItem, SerialNumberScan, ScanSession

logger = logging.getLogger("apps.scanning")


class ValidationError:
    """Structured validation error."""
    def __init__(self, code: str, message: str, retryable: bool = True):
        self.code = code
        self.message = message
        self.retryable = retryable

    def __repr__(self):
        return f"ValidationError({self.code}: {self.message})"


def validate_session_state(session: ScanSession) -> ValidationError | None:
    """Check that session is in a scannable state."""
    if session.status not in session.SCANNABLE_STATUSES:
        return ValidationError(
            code="SESSION_INVALID_STATE",
            message=f"Session is in state '{session.status}' and cannot accept scans.",
            retryable=False,
        )
    return None


def validate_serial_against_profile(
    serial: str,
    item: HUContentItem,
) -> ValidationError | None:
    """Validate serial number against the item's SN profile."""
    if not item.sn_profile:
        # No profile linked — skip profile validation
        # (item may have sn_profile_code but no matching SNProfile object)
        if item.sn_profile_code:
            logger.warning(
                "Item %s has sn_profile_code='%s' but no linked SNProfile object",
                item.material_number, item.sn_profile_code,
            )
        return None

    is_valid, rejection_code = item.sn_profile.validate_serial(serial)
    if not is_valid:
        return ValidationError(
            code=rejection_code,
            message=f"Serial '{serial}' does not match profile {item.sn_profile.code}: {rejection_code}",
        )
    return None


def validate_no_local_duplicate(
    session: ScanSession,
    serial: str,
) -> ValidationError | None:
    """Check that serial has not already been scanned in this session."""
    exists = SerialNumberScan.objects.filter(
        session=session,
        scanned_serial=serial,
        is_valid=True,
    ).exists()

    if exists:
        return ValidationError(
            code="SN_DUPLICATE_LOCAL",
            message=f"Serial '{serial}' has already been scanned in this session.",
            retryable=True,
        )
    return None


def validate_quantity_not_exceeded(item: HUContentItem) -> ValidationError | None:
    """Check that item still has remaining quantity to scan."""
    if item.is_fully_scanned:
        return ValidationError(
            code="SN_QTY_EXCEEDED",
            message=f"Item '{item.material_number}' already fully scanned ({item.scanned_qty}/{item.expected_qty}).",
            retryable=False,
        )
    return None


def validate_scan(
    session: ScanSession,
    item: HUContentItem,
    serial: str,
) -> ValidationError | None:
    """
    Run all validation checks for a scan attempt.
    Returns None if valid, or the first ValidationError found.
    """
    # 1. Session state
    err = validate_session_state(session)
    if err:
        return err

    # 2. Quantity guard
    err = validate_quantity_not_exceeded(item)
    if err:
        return err

    # 3. Local duplicate
    err = validate_no_local_duplicate(session, serial)
    if err:
        return err

    # 4. Profile validation
    err = validate_serial_against_profile(serial, item)
    if err:
        return err

    return None
