"""Tests for GS1 DataMatrix barcode parsing."""
from apps.scanning.services.gs1 import parse_gs1


class TestGS1Parser:
    """GS1 DataMatrix parsing with ]2d prefix and AI codes."""

    def test_gs1_with_manufacturing_part_and_serial(self):
        """AI(240) manufacturing part + AI(21) serial via GS separator."""
        raw = "]2d240PLB3272UHS-B1\x1d211234567890123"
        result = parse_gs1(raw)
        assert result.is_gs1 is True
        assert result.manufacturing_part_number == "PLB3272UHS-B1"
        assert result.serial_number == "1234567890123"
        assert result.ai_map["240"] == "PLB3272UHS-B1"
        assert result.ai_map["21"] == "1234567890123"

    def test_gs1_serial_only(self):
        """GS1 with only AI(21) serial number."""
        raw = "]2d211999888777666"
        result = parse_gs1(raw)
        assert result.is_gs1 is True
        assert result.serial_number == "1999888777666"
        assert result.manufacturing_part_number == ""

    def test_gs1_manufacturing_part_only(self):
        """GS1 with only AI(240) — no serial. Should warn."""
        raw = "]2d240PLB3272UHS-B1"
        result = parse_gs1(raw)
        assert result.is_gs1 is True
        assert result.manufacturing_part_number == "PLB3272UHS-B1"
        assert result.serial_number == ""
        # No error since mfr part found, but no serial

    def test_gs1_uppercase_prefix(self):
        """]2D (uppercase) is also valid."""
        raw = "]2D240TEST-PART\x1d21SERIAL123"
        result = parse_gs1(raw)
        assert result.is_gs1 is True
        assert result.manufacturing_part_number == "TEST-PART"
        assert result.serial_number == "SERIAL123"

    def test_not_gs1(self):
        """Non-GS1 input returns is_gs1=False."""
        result = parse_gs1("1234567890123")
        assert result.is_gs1 is False

    def test_gs1_empty_after_prefix(self):
        """Just the prefix with nothing after."""
        result = parse_gs1("]2d")
        assert result.is_gs1 is True
        assert result.error  # Should have error about no data

    def test_gs1_with_gtin(self):
        """GS1 with AI(01) GTIN + AI(21) serial."""
        raw = "]2d0104948570121830\x1d211234567890123"
        result = parse_gs1(raw)
        assert result.is_gs1 is True
        assert result.gtin == "04948570121830"
        assert result.serial_number == "1234567890123"

    def test_gs1_multiple_ais(self):
        """Full GS1 with GTIN + manufacturing part + serial."""
        raw = "]2d0104948570121830\x1d240PLB3272UHS-B1\x1d211234567890123"
        result = parse_gs1(raw)
        assert result.is_gs1 is True
        assert result.gtin == "04948570121830"
        assert result.manufacturing_part_number == "PLB3272UHS-B1"
        assert result.serial_number == "1234567890123"

    def test_gs1_serial_at_end_no_gs(self):
        """Serial at end of string without trailing GS separator."""
        raw = "]2d240PARTNUM\x1d21SN-AT-END"
        result = parse_gs1(raw)
        assert result.serial_number == "SN-AT-END"

    def test_gs1_strips_whitespace_in_values(self):
        """Values should be stripped of whitespace."""
        raw = "]2d240 PLB3272UHS \x1d21 1234567890123 "
        result = parse_gs1(raw)
        assert result.manufacturing_part_number == "PLB3272UHS"
        assert result.serial_number == "1234567890123"
