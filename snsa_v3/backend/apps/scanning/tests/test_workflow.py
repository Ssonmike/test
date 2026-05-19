"""Integration tests for scan workflow orchestrator."""
from unittest.mock import patch
from django.test import TestCase

from apps.acf.schemas import AcfHUResponse, AcfItem
from apps.scanning.models import (
    ScanSession, HUContentItem, SerialNumberScan, SNProfile, ScanLog,
)
from apps.scanning.services.workflow import lookup_hu, process_scan, complete_session


def _mock_acf_response_single_gs1():
    return AcfHUResponse(
        hu_number="HU_SINGLE_GS1",
        items=[
            AcfItem(
                material="PLB3272UHS", description="Monitor 32\"",
                expected_qty=2, sn_profile="II01", is_serialised=True,
                batch="B001", delivery_ref="D001",
                manufacturing_part_number="PLB3272UHS-B1",
                ean_code="4948570121830", uom="EA",
            ),
        ],
    )


def _mock_acf_response_multi():
    return AcfHUResponse(
        hu_number="HU_MULTI",
        items=[
            AcfItem(
                material="PLB3272UHS", description="Monitor 32\"",
                expected_qty=1, sn_profile="II01", is_serialised=True,
                batch="B002", delivery_ref="D002",
                manufacturing_part_number="PLB3272UHS-B1",
                ean_code="4948570121830", uom="EA",
            ),
            AcfItem(
                material="ACC-WEB-01", description="Webcam",
                expected_qty=1, sn_profile="II02", is_serialised=True,
                batch="B002", delivery_ref="D002",
                manufacturing_part_number="ACC-WEB-01-BK",
                ean_code="4948570118458", uom="EA",
            ),
        ],
    )


def _mock_acf_response_no_serial():
    return AcfHUResponse(
        hu_number="HU_NO_SERIAL",
        items=[
            AcfItem(
                material="CABLE-01", description="Cable",
                expected_qty=10, sn_profile="", is_serialised=False,
                batch="B003", delivery_ref="D003",
            ),
        ],
    )


class LookupTest(TestCase):
    def setUp(self):
        SNProfile.objects.get_or_create(code="II01", defaults={"name": "Monitors", "prefix_char": "1", "expected_length": 13})
        SNProfile.objects.get_or_create(code="II02", defaults={"name": "Accessories", "prefix_char": "0", "expected_length": 13})

    @patch("apps.scanning.services.workflow.ACFClient")
    def test_lookup_single_sku(self, MockClient):
        MockClient.return_value.get_hu.return_value = _mock_acf_response_single_gs1()
        result = lookup_hu("HU_SINGLE_GS1")
        assert result.success is True
        session = result.session
        assert session.flow_type == ScanSession.FLOW_SINGLE_SKU
        assert session.status == ScanSession.STATUS_READY_TO_SCAN
        assert session.content_items.count() == 1
        item = session.content_items.first()
        assert item.is_serialised is True
        assert item.manufacturing_part_number == "PLB3272UHS-B1"
        assert item.sn_profile is not None
        assert item.sn_profile.code == "II01"

    @patch("apps.scanning.services.workflow.ACFClient")
    def test_lookup_multi_sku(self, MockClient):
        MockClient.return_value.get_hu.return_value = _mock_acf_response_multi()
        result = lookup_hu("HU_MULTI")
        assert result.success is True
        assert result.session.flow_type == ScanSession.FLOW_MULTI_SKU
        assert result.session.content_items.filter(is_serialised=True).count() == 2

    @patch("apps.scanning.services.workflow.ACFClient")
    def test_lookup_no_serialization(self, MockClient):
        MockClient.return_value.get_hu.return_value = _mock_acf_response_no_serial()
        result = lookup_hu("HU_NO_SERIAL")
        assert result.success is True
        assert result.session.status == ScanSession.STATUS_NO_SERIALIZATION
        assert result.session.flow_type == ScanSession.FLOW_NO_SERIALIZATION

    @patch("apps.scanning.services.workflow.ACFClient")
    def test_lookup_hu_not_found(self, MockClient):
        from apps.acf.client import ACFError
        MockClient.return_value.get_hu.side_effect = ACFError("HU not found in SAP: HU_NOPE (404)")
        result = lookup_hu("HU_NOPE")
        assert result.success is False
        assert result.error_code == "HU_NOT_FOUND"

    @patch("apps.scanning.services.workflow.ACFClient")
    def test_lookup_acf_failure(self, MockClient):
        from apps.acf.client import ACFError
        MockClient.return_value.get_hu.side_effect = ACFError("ACF timeout")
        result = lookup_hu("HU_TIMEOUT")
        assert result.success is False
        assert result.error_code == "ACF_LOOKUP_FAILED"

    @patch("apps.scanning.services.workflow.ACFClient")
    def test_lookup_recovers_active_session(self, MockClient):
        """Re-scanning an HU with active session returns existing session."""
        MockClient.return_value.get_hu.return_value = _mock_acf_response_single_gs1()
        r1 = lookup_hu("HU_SINGLE_GS1")
        r2 = lookup_hu("HU_SINGLE_GS1")
        assert r1.session.id == r2.session.id
        assert MockClient.return_value.get_hu.call_count == 1


class SingleSKUGS1FlowTest(TestCase):
    def setUp(self):
        SNProfile.objects.get_or_create(code="II01", defaults={"name": "Monitors", "prefix_char": "1", "expected_length": 13})
        self.session = ScanSession.objects.create(
            hu_number="HU_T", status=ScanSession.STATUS_READY_TO_SCAN,
            flow_type=ScanSession.FLOW_SINGLE_SKU,
        )
        self.item = HUContentItem.objects.create(
            session=self.session, material_number="PLB3272UHS",
            description="Monitor", expected_qty=2, is_serialised=True,
            sn_profile=SNProfile.objects.get(code="II01"), sn_profile_code="II01",
            manufacturing_part_number="PLB3272UHS-B1", ean_code="4948570121830",
        )

    def test_gs1_scan_success(self):
        scan_input = "]2d240PLB3272UHS-B1\x1d211111111111111"
        result = process_scan(self.session, scan_input)
        assert result.accepted is True
        assert result.barcode_type == "gs1"
        assert result.serial_number == "1111111111111"
        assert result.remaining_for_item == 1
        self.item.refresh_from_db()
        assert self.item.scanned_qty == 1

    def test_gs1_scan_completes_session(self):
        """Two scans complete the session — does NOT auto-push."""
        process_scan(self.session, "]2d240PLB3272UHS-B1\x1d211111111111111")
        result = process_scan(self.session, "]2d240PLB3272UHS-B1\x1d211222222222222")
        assert result.accepted is True
        assert result.session_ready_to_complete is True
        self.session.refresh_from_db()
        assert self.session.status == ScanSession.STATUS_READY_TO_COMPLETE

    def test_duplicate_rejection(self):
        process_scan(self.session, "]2d240PLB3272UHS-B1\x1d211111111111111")
        result = process_scan(self.session, "]2d240PLB3272UHS-B1\x1d211111111111111")
        assert result.accepted is False
        assert result.error_code == "SN_DUPLICATE_LOCAL"

    def test_wrong_prefix_rejection(self):
        result = process_scan(self.session, "]2d240PLB3272UHS-B1\x1d210WRONG_PREFIX")
        assert result.accepted is False
        assert result.error_code == "SN_PREFIX_MISMATCH"

    def test_wrong_length_rejection(self):
        result = process_scan(self.session, "]2d240PLB3272UHS-B1\x1d211SHORT")
        assert result.accepted is False
        assert result.error_code == "SN_LENGTH_MISMATCH"

    def test_item_not_on_hu(self):
        result = process_scan(self.session, "]2d240NONEXISTENT\x1d211111111111111")
        assert result.accepted is False
        assert result.error_code == "ITEM_NOT_ON_HU"


class SingleSKUEANFlowTest(TestCase):
    def setUp(self):
        SNProfile.objects.get_or_create(code="II01", defaults={"name": "Monitors", "prefix_char": "1", "expected_length": 13})
        self.session = ScanSession.objects.create(
            hu_number="HU_E", status=ScanSession.STATUS_READY_TO_SCAN,
            flow_type=ScanSession.FLOW_SINGLE_SKU,
        )
        self.item = HUContentItem.objects.create(
            session=self.session, material_number="PLB2483HSU",
            description="Monitor 24\"", expected_qty=2, is_serialised=True,
            sn_profile=SNProfile.objects.get(code="II01"), sn_profile_code="II01",
            ean_code="4948570118458",
        )

    def test_ean_then_serial_flow(self):
        """Scan EAN first → sets pending item. Then scan serial → accepted."""
        r1 = process_scan(self.session, "4948570118458")
        assert r1.accepted is False
        assert r1.awaiting_serial is True
        assert r1.matched_item_id == self.item.id
        self.session.refresh_from_db()
        assert self.session.pending_item_id == self.item.id

        r2 = process_scan(self.session, "1111111111111")
        assert r2.accepted is True
        assert r2.serial_number == "1111111111111"

    def test_serial_only_single_sku(self):
        """In single SKU, serial can match via profile without EAN first."""
        result = process_scan(self.session, "1222222222222")
        assert result.accepted is True
        assert result.serial_number == "1222222222222"


class MultiSKUFlowTest(TestCase):
    def setUp(self):
        SNProfile.objects.get_or_create(code="II01", defaults={"name": "Monitors", "prefix_char": "1", "expected_length": 13})
        SNProfile.objects.get_or_create(code="II02", defaults={"name": "Accessories", "prefix_char": "0", "expected_length": 13})
        self.session = ScanSession.objects.create(
            hu_number="HU_M", status=ScanSession.STATUS_READY_TO_SCAN,
            flow_type=ScanSession.FLOW_MULTI_SKU,
        )
        self.monitor = HUContentItem.objects.create(
            session=self.session, material_number="MON-01",
            expected_qty=1, is_serialised=True,
            sn_profile=SNProfile.objects.get(code="II01"), sn_profile_code="II01",
            manufacturing_part_number="MON-01-B1", ean_code="4948570121830",
        )
        self.acc = HUContentItem.objects.create(
            session=self.session, material_number="ACC-01",
            expected_qty=1, is_serialised=True,
            sn_profile=SNProfile.objects.get(code="II02"), sn_profile_code="II02",
            manufacturing_part_number="ACC-01-BK", ean_code="4948570118458",
        )

    def test_gs1_multi_sku(self):
        r1 = process_scan(self.session, "]2d240MON-01-B1\x1d211111111111111")
        assert r1.accepted is True
        assert r1.matched_item_id == self.monitor.id

        r2 = process_scan(self.session, "]2d240ACC-01-BK\x1d210222222222222")
        assert r2.accepted is True
        assert r2.matched_item_id == self.acc.id
        assert r2.session_ready_to_complete is True

    def test_ean_serial_multi_sku(self):
        # Scan EAN for monitor
        r1 = process_scan(self.session, "4948570121830")
        assert r1.awaiting_serial is True

        # Scan serial for monitor
        r2 = process_scan(self.session, "1333333333333")
        assert r2.accepted is True

        # Pending context should be cleared for multi SKU
        self.session.refresh_from_db()
        assert self.session.pending_item_id is None

    def test_serial_only_unambiguous_multi(self):
        """Different profiles allow serial-only matching even in multi SKU."""
        r1 = process_scan(self.session, "1444444444444")  # II01 → monitor
        assert r1.accepted is True
        assert r1.matched_item_id == self.monitor.id

        r2 = process_scan(self.session, "0555555555555")  # II02 → accessory
        assert r2.accepted is True
        assert r2.matched_item_id == self.acc.id

    def test_quantity_exceeded(self):
        process_scan(self.session, "1666666666666")  # Fill monitor
        result = process_scan(self.session, "1777777777777")  # Over qty
        assert result.accepted is False
        assert result.error_code in ("SN_QTY_EXCEEDED", "SN_NO_MATCH")


class CompletionFlowTest(TestCase):
    def setUp(self):
        SNProfile.objects.get_or_create(code="II01", defaults={"name": "Monitors", "prefix_char": "1", "expected_length": 13})
        self.session = ScanSession.objects.create(
            hu_number="HU_C", status=ScanSession.STATUS_READY_TO_COMPLETE,
            flow_type=ScanSession.FLOW_SINGLE_SKU,
        )
        self.item = HUContentItem.objects.create(
            session=self.session, material_number="MON-C",
            expected_qty=1, scanned_qty=1, is_serialised=True,
            sn_profile=SNProfile.objects.get(code="II01"), sn_profile_code="II01",
        )
        SerialNumberScan.objects.create(
            session=self.session, content_item=self.item,
            raw_input="1888888888888", scanned_serial="1888888888888",
            is_valid=True, barcode_type="serial",
        )

    @patch("apps.scanning.services.workflow.ACFClient")
    def test_complete_success(self, MockClient):
        MockClient.return_value.push_serials.return_value = {"sap_document_ref": "490001"}
        success, ref, err = complete_session(self.session)
        assert success is True
        assert ref == "490001"
        self.session.refresh_from_db()
        assert self.session.status == ScanSession.STATUS_COMPLETED

    @patch("apps.scanning.services.workflow.ACFClient")
    def test_complete_failure_preserves_data(self, MockClient):
        from apps.acf.client import ACFError
        MockClient.return_value.push_serials.side_effect = ACFError("SAP rejected")
        success, ref, err = complete_session(self.session)
        assert success is False
        assert "SAP rejected" in err
        self.session.refresh_from_db()
        assert self.session.status == ScanSession.STATUS_SAP_PUSH_FAILED
        # Scans preserved
        assert self.session.scans.filter(is_valid=True).count() == 1

    @patch("apps.scanning.services.workflow.ACFClient")
    def test_complete_idempotent(self, MockClient):
        MockClient.return_value.push_serials.return_value = {"sap_document_ref": "490002"}
        complete_session(self.session)
        # Second call should succeed without calling ACF again
        success, ref, err = complete_session(self.session)
        assert success is True
        assert MockClient.return_value.push_serials.call_count == 1

    @patch("apps.scanning.services.workflow.ACFClient")
    def test_retry_after_failure(self, MockClient):
        from apps.acf.client import ACFError
        MockClient.return_value.push_serials.side_effect = ACFError("fail")
        complete_session(self.session)
        self.session.refresh_from_db()
        assert self.session.status == ScanSession.STATUS_SAP_PUSH_FAILED

        # Retry
        MockClient.return_value.push_serials.side_effect = None
        MockClient.return_value.push_serials.return_value = {"sap_document_ref": "490003"}
        success, ref, err = complete_session(self.session)
        assert success is True
        self.session.refresh_from_db()
        assert self.session.status == ScanSession.STATUS_COMPLETED

    def test_cannot_complete_wrong_state(self):
        self.session.status = ScanSession.STATUS_SCAN_IN_PROGRESS
        self.session.save()
        success, ref, err = complete_session(self.session)
        assert success is False
        assert "Cannot complete" in err


class AuditTrailTest(TestCase):
    def setUp(self):
        SNProfile.objects.get_or_create(code="II01", defaults={"name": "Monitors", "prefix_char": "1", "expected_length": 13})
        self.session = ScanSession.objects.create(
            hu_number="HU_A", status=ScanSession.STATUS_READY_TO_SCAN,
            flow_type=ScanSession.FLOW_SINGLE_SKU,
        )
        self.item = HUContentItem.objects.create(
            session=self.session, material_number="MON-A",
            expected_qty=2, is_serialised=True,
            sn_profile=SNProfile.objects.get(code="II01"), sn_profile_code="II01",
            manufacturing_part_number="MON-A-B1",
        )

    def test_invalid_scans_are_recorded(self):
        """Invalid scans must be stored for audit."""
        process_scan(self.session, "]2d240MON-A-B1\x1d210WRONG_PREFIX")
        all_scans = SerialNumberScan.objects.filter(session=self.session)
        assert all_scans.count() == 1
        scan = all_scans.first()
        assert scan.is_valid is False
        assert scan.rejection_code == "SN_PREFIX_MISMATCH"

    def test_valid_scan_logged(self):
        process_scan(self.session, "]2d240MON-A-B1\x1d211999999999999")
        logs = ScanLog.objects.filter(session=self.session, event_type="scan_accepted")
        assert logs.count() == 1

    def test_rejected_scan_logged(self):
        process_scan(self.session, "]2d240MON-A-B1\x1d210BAD_PREFIX_01")
        logs = ScanLog.objects.filter(session=self.session, event_type="scan_rejected")
        assert logs.count() == 1
