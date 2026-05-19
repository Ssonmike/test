"""Tests for barcode type detection and input normalization."""
from apps.scanning.services.barcodes import (
    detect_and_parse, normalize_input, is_ean13, is_hu_barcode,
)


class TestNormalization:
    def test_strips_whitespace(self):
        assert normalize_input("  hello  ") == "hello"

    def test_strips_cr_lf(self):
        assert normalize_input("hello\r\n") == "hello"

    def test_strips_tabs(self):
        assert normalize_input("\thello\t") == "hello"

    def test_removes_null_bytes(self):
        assert normalize_input("hel\x00lo") == "hello"

    def test_preserves_gs_char(self):
        """GS (0x1D) is used by GS1 and must be preserved."""
        result = normalize_input("abc\x1ddef")
        assert "\x1d" in result


class TestEAN13Detection:
    def test_valid_ean13(self):
        # 4948570121830 — valid check digit
        assert is_ean13("4948570121830") is True

    def test_invalid_check_digit(self):
        assert is_ean13("4948570121831") is False

    def test_wrong_length(self):
        assert is_ean13("123456789012") is False  # 12 digits
        assert is_ean13("12345678901234") is False  # 14 digits

    def test_non_numeric(self):
        assert is_ean13("494857012183A") is False

    def test_another_valid_ean(self):
        assert is_ean13("4948570118458") is True


class TestHUBarcodeDetection:
    def test_hu_prefix(self):
        assert is_hu_barcode("HU0001") is True
        assert is_hu_barcode("HU_SINGLE_GS1") is True

    def test_hu_case_insensitive(self):
        assert is_hu_barcode("hu0001") is True

    def test_sscc18(self):
        assert is_hu_barcode("003456789012345678") is True

    def test_not_hu(self):
        assert is_hu_barcode("PLB3272UHS") is False
        assert is_hu_barcode("1234567890123") is False  # 13 digits = EAN


class TestDetectAndParse:
    def test_gs1_datamatrix(self):
        raw = "]2d240PLB3272UHS-B1\x1d211234567890123"
        result = detect_and_parse(raw)
        assert result.barcode_type == "gs1"
        assert result.manufacturing_part_number == "PLB3272UHS-B1"
        assert result.serial_number == "1234567890123"

    def test_ean13(self):
        result = detect_and_parse("4948570121830")
        assert result.barcode_type == "ean"
        assert result.ean_code == "4948570121830"

    def test_hu_barcode(self):
        result = detect_and_parse("HU_SINGLE_GS1")
        assert result.barcode_type == "hu"

    def test_serial_number_fallback(self):
        result = detect_and_parse("1ABCDEF012345")
        assert result.barcode_type == "serial"
        assert result.serial_number == "1ABCDEF012345"

    def test_empty_input(self):
        result = detect_and_parse("")
        assert result.barcode_type == "unknown"
        assert result.error

    def test_whitespace_only(self):
        result = detect_and_parse("   ")
        assert result.barcode_type == "unknown"

    def test_serial_with_prefix_char(self):
        """Serial starting with '1' and length 13 — should be serial, not EAN (not all digits)."""
        result = detect_and_parse("1ABCDE1234567")
        assert result.barcode_type == "serial"

    def test_gs1_priority_over_ean(self):
        """GS1 prefix takes priority even if content could look like EAN."""
        result = detect_and_parse("]2d211234567890123")
        assert result.barcode_type == "gs1"
