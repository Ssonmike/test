from dataclasses import dataclass

from apps.scanning.models import HUContentItem, ScanSession


@dataclass
class MatchResult:
    """Result of attempting to match a scan to a content item."""
    matched: bool = False
    item: HUContentItem | None = None
    matched_by: str = "none"  # gs1, ean, serial_profile, pending_context, manual
    error_code: str = ""
    error_message: str = ""
    ambiguous_items: list = None

    def __post_init__(self):
        if self.ambiguous_items is None:
            self.ambiguous_items = []


def match_by_manufacturing_part(
    session: ScanSession,
    manufacturing_part: str,
) -> MatchResult:
    """Match by manufacturing part number from GS1 AI(240)."""
    if not manufacturing_part:
        return MatchResult(error_code="NO_PART_NUMBER", error_message="No manufacturing part number provided")

    items = list(
        session.content_items.filter(
            is_serialised=True,
            manufacturing_part_number__iexact=manufacturing_part,
        )
    )

    if not items:
        return MatchResult(
            error_code="ITEM_NOT_ON_HU",
            error_message=f"Manufacturing part '{manufacturing_part}' not found on this HU",
        )

    if len(items) > 1:
        return MatchResult(
            error_code="SN_AMBIGUOUS",
            error_message=f"Multiple items match manufacturing part '{manufacturing_part}'",
            ambiguous_items=items,
        )

    return MatchResult(matched=True, item=items[0], matched_by="gs1")


def match_by_ean(session: ScanSession, ean_code: str) -> MatchResult:
    """Match by EAN code."""
    if not ean_code:
        return MatchResult(error_code="NO_EAN", error_message="No EAN code provided")

    items = list(
        session.content_items.filter(
            is_serialised=True,
            ean_code=ean_code,
        )
    )

    if not items:
        return MatchResult(
            error_code="ITEM_NOT_ON_HU",
            error_message=f"EAN '{ean_code}' not found on this HU",
        )

    if len(items) > 1:
        return MatchResult(
            error_code="SN_AMBIGUOUS",
            error_message=f"Multiple items match EAN '{ean_code}'",
            ambiguous_items=items,
        )

    return MatchResult(matched=True, item=items[0], matched_by="ean_then_serial")


def match_by_serial_profile(
    session: ScanSession,
    serial: str,
) -> MatchResult:
    """
    Match by SN profile rules (prefix char + length).
    Only returns a match if exactly one serialised item's profile matches.
    """
    if not serial:
        return MatchResult(error_code="NO_SERIAL", error_message="No serial number provided")

    candidates = []
    for item in session.content_items.filter(is_serialised=True):
        if not item.sn_profile:
            continue
        is_valid, _ = item.sn_profile.validate_serial(serial)
        if is_valid and not item.is_fully_scanned:
            candidates.append(item)

    if not candidates:
        # Check if it matches any profile at all (even fully scanned items)
        all_items = session.content_items.filter(is_serialised=True)
        for item in all_items:
            if item.sn_profile:
                is_valid, _ = item.sn_profile.validate_serial(serial)
                if is_valid and item.is_fully_scanned:
                    return MatchResult(
                        error_code="SN_QTY_EXCEEDED",
                        error_message=f"Item '{item.material_number}' already fully scanned",
                        item=item,
                    )
        return MatchResult(
            error_code="SN_NO_MATCH",
            error_message="Serial does not match any item's SN profile on this HU",
        )

    if len(candidates) > 1:
        return MatchResult(
            error_code="SN_AMBIGUOUS",
            error_message="Serial matches multiple items' SN profiles",
            ambiguous_items=candidates,
        )

    return MatchResult(matched=True, item=candidates[0], matched_by="serial_only")


def match_item(
    session: ScanSession,
    manufacturing_part: str = "",
    ean_code: str = "",
    serial: str = "",
    manual_item_id: int | None = None,
    pending_item_id: int | None = None,
) -> MatchResult:
    # 1. Manual disambiguation
    if manual_item_id:
        try:
            item = session.content_items.get(pk=manual_item_id, is_serialised=True)
            return MatchResult(matched=True, item=item, matched_by="manual_fallback")
        except HUContentItem.DoesNotExist:
            return MatchResult(
                error_code="ITEM_NOT_ON_HU",
                error_message=f"Manual item ID {manual_item_id} not found on this HU",
            )

    # 2. Manufacturing part number
    if manufacturing_part:
        result = match_by_manufacturing_part(session, manufacturing_part)
        if result.matched or result.error_code not in ("NO_PART_NUMBER",):
            return result

    # 3. EAN code
    if ean_code:
        result = match_by_ean(session, ean_code)
        if result.matched or result.error_code not in ("NO_EAN",):
            return result

    # 4. Pending item context
    if pending_item_id:
        try:
            item = session.content_items.get(pk=pending_item_id, is_serialised=True)
            if item.is_fully_scanned:
                return MatchResult(
                    error_code="SN_QTY_EXCEEDED",
                    error_message=f"Item '{item.material_number}' already fully scanned",
                    item=item,
                )
            return MatchResult(matched=True, item=item, matched_by="pending_context")
        except HUContentItem.DoesNotExist:
            pass

    # 5. Serial profile match (for single SKU or unambiguous multi SKU)
    if serial:
        return match_by_serial_profile(session, serial)

    return MatchResult(
        error_code="SN_NO_MATCH",
        error_message="Cannot resolve item from scan data",
    )
