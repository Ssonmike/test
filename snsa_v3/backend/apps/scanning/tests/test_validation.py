"""Tests for validation engine and item matching."""
from django.test import TestCase

from apps.scanning.models import (
    ScanSession, HUContentItem, SerialNumberScan, SNProfile,
)
from apps.scanning.services.validation import (
    validate_scan, validate_session_state, validate_serial_against_profile,
    validate_no_local_duplicate, validate_quantity_not_exceeded,
)
from apps.scanning.services.matching import (
    match_item, match_by_manufacturing_part, match_by_ean, match_by_serial_profile,
)


class SNProfileValidationTest(TestCase):
    def setUp(self):
        self.ii01, _ = SNProfile.objects.get_or_create(
            code="II01",
            defaults={"name": "Monitors", "prefix_char": "1", "expected_length": 13},
        )
        self.ii02, _ = SNProfile.objects.get_or_create(
            code="II02",
            defaults={"name": "Accessories", "prefix_char": "0", "expected_length": 13},
        )
        self.ii03, _ = SNProfile.objects.get_or_create(
            code="II03",
            defaults={"name": "USB Adapters", "prefix_char": "E", "expected_length": 18},
        )

    def test_ii01_valid(self):
        ok, err = self.ii01.validate_serial("1234567890123")
        assert ok is True
        assert err is None

    def test_ii01_wrong_prefix(self):
        ok, err = self.ii01.validate_serial("0234567890123")
        assert ok is False
        assert "PREFIX" in err

    def test_ii01_wrong_length(self):
        ok, err = self.ii01.validate_serial("123456789012")  # 12 chars
        assert ok is False
        assert "LENGTH" in err

    def test_ii02_valid(self):
        ok, err = self.ii02.validate_serial("0123456789012")
        assert ok is True

    def test_ii03_valid(self):
        ok, err = self.ii03.validate_serial("E12345678901234567")
        assert ok is True

    def test_ii03_wrong_prefix(self):
        ok, err = self.ii03.validate_serial("X12345678901234567")
        assert ok is False


class MatchingTest(TestCase):
    def setUp(self):
        self.ii01, _ = SNProfile.objects.get_or_create(
            code="II01",
            defaults={"name": "Monitors", "prefix_char": "1", "expected_length": 13},
        )
        self.ii02, _ = SNProfile.objects.get_or_create(
            code="II02",
            defaults={"name": "Accessories", "prefix_char": "0", "expected_length": 13},
        )
        self.session = ScanSession.objects.create(
            hu_number="HU_TEST", status=ScanSession.STATUS_READY_TO_SCAN,
            flow_type=ScanSession.FLOW_MULTI_SKU,
        )
        self.item_a = HUContentItem.objects.create(
            session=self.session, material_number="MONITOR-A",
            description="Monitor A", expected_qty=2, is_serialised=True,
            sn_profile=self.ii01, sn_profile_code="II01",
            manufacturing_part_number="MON-A-B1", ean_code="4948570121830",
        )
        self.item_b = HUContentItem.objects.create(
            session=self.session, material_number="ACCESSORY-B",
            description="Accessory B", expected_qty=1, is_serialised=True,
            sn_profile=self.ii02, sn_profile_code="II02",
            manufacturing_part_number="ACC-B-BK", ean_code="4948570118458",
        )

    def test_match_by_manufacturing_part(self):
        result = match_by_manufacturing_part(self.session, "MON-A-B1")
        assert result.matched is True
        assert result.item.id == self.item_a.id

    def test_match_by_manufacturing_part_not_found(self):
        result = match_by_manufacturing_part(self.session, "NONEXISTENT")
        assert result.matched is False
        assert result.error_code == "ITEM_NOT_ON_HU"

    def test_match_by_ean(self):
        result = match_by_ean(self.session, "4948570121830")
        assert result.matched is True
        assert result.item.id == self.item_a.id

    def test_match_by_ean_not_found(self):
        result = match_by_ean(self.session, "0000000000000")
        assert result.matched is False
        assert result.error_code == "ITEM_NOT_ON_HU"

    def test_match_by_serial_profile_unambiguous(self):
        """II01 prefix '1' matches only monitor, II02 prefix '0' matches only accessory."""
        result = match_by_serial_profile(self.session, "1234567890123")
        assert result.matched is True
        assert result.item.id == self.item_a.id

        result = match_by_serial_profile(self.session, "0123456789012")
        assert result.matched is True
        assert result.item.id == self.item_b.id

    def test_match_by_serial_profile_no_match(self):
        result = match_by_serial_profile(self.session, "XXXXXXXXXXX")
        assert result.matched is False
        assert result.error_code == "SN_NO_MATCH"

    def test_match_item_priority_manufacturing_part(self):
        """Manufacturing part takes priority over serial profile."""
        result = match_item(
            self.session,
            manufacturing_part="MON-A-B1",
            serial="1234567890123",
        )
        assert result.matched is True
        assert result.matched_by == "gs1"

    def test_match_item_ean_fallback(self):
        result = match_item(self.session, ean_code="4948570118458")
        assert result.matched is True
        assert result.item.id == self.item_b.id

    def test_match_item_manual_override(self):
        result = match_item(self.session, manual_item_id=self.item_b.id)
        assert result.matched is True
        assert result.matched_by == "manual_fallback"

    def test_match_item_pending_context(self):
        result = match_item(
            self.session,
            serial="0123456789012",
            pending_item_id=self.item_b.id,
        )
        assert result.matched is True
        assert result.matched_by == "pending_context"


class AmbiguousMatchTest(TestCase):
    def setUp(self):
        self.ii01, _ = SNProfile.objects.get_or_create(
            code="II01",
            defaults={"name": "Monitors", "prefix_char": "1", "expected_length": 13},
        )
        self.session = ScanSession.objects.create(
            hu_number="HU_AMB", status=ScanSession.STATUS_READY_TO_SCAN,
            flow_type=ScanSession.FLOW_MULTI_SKU,
        )
        # Two items with same SN profile
        self.item_x = HUContentItem.objects.create(
            session=self.session, material_number="MON-X",
            expected_qty=1, is_serialised=True,
            sn_profile=self.ii01, sn_profile_code="II01",
            ean_code="1111111111116",
        )
        self.item_y = HUContentItem.objects.create(
            session=self.session, material_number="MON-Y",
            expected_qty=1, is_serialised=True,
            sn_profile=self.ii01, sn_profile_code="II01",
            ean_code="2222222222222",
        )

    def test_serial_profile_ambiguous(self):
        result = match_by_serial_profile(self.session, "1234567890123")
        assert result.matched is False
        assert result.error_code == "SN_AMBIGUOUS"
        assert len(result.ambiguous_items) == 2


class ValidationTest(TestCase):
    def setUp(self):
        self.ii01, _ = SNProfile.objects.get_or_create(
            code="II01",
            defaults={"name": "Monitors", "prefix_char": "1", "expected_length": 13},
        )
        self.session = ScanSession.objects.create(
            hu_number="HU_VAL", status=ScanSession.STATUS_SCAN_IN_PROGRESS,
            flow_type=ScanSession.FLOW_SINGLE_SKU,
        )
        self.item = HUContentItem.objects.create(
            session=self.session, material_number="MON-V",
            expected_qty=2, is_serialised=True,
            sn_profile=self.ii01, sn_profile_code="II01",
        )

    def test_valid_scan(self):
        err = validate_scan(self.session, self.item, "1234567890123")
        assert err is None

    def test_session_wrong_state(self):
        self.session.status = ScanSession.STATUS_COMPLETED
        self.session.save()
        err = validate_session_state(self.session)
        assert err is not None
        assert err.code == "SESSION_INVALID_STATE"

    def test_duplicate_local(self):
        SerialNumberScan.objects.create(
            session=self.session, content_item=self.item,
            raw_input="1234567890123", scanned_serial="1234567890123",
            is_valid=True,
        )
        err = validate_no_local_duplicate(self.session, "1234567890123")
        assert err is not None
        assert err.code == "SN_DUPLICATE_LOCAL"

    def test_quantity_exceeded(self):
        self.item.scanned_qty = 2
        self.item.save()
        err = validate_quantity_not_exceeded(self.item)
        assert err is not None
        assert err.code == "SN_QTY_EXCEEDED"

    def test_wrong_prefix(self):
        err = validate_serial_against_profile("0234567890123", self.item)
        assert err is not None
        assert err.code == "SN_PREFIX_MISMATCH"

    def test_wrong_length(self):
        err = validate_serial_against_profile("123456789012", self.item)
        assert err is not None
        assert err.code == "SN_LENGTH_MISMATCH"
