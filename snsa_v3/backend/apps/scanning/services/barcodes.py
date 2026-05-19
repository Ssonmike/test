"""
Barcode type detection and input normalization for warehouse scanning.
Supports:
  - GS1 DataMatrix (prefix ]2d, contains AI codes)
  - EAN-13 (exactly 13 digits)
  - HU barcode (warehouse HU patterns)
  - Serial number (fallback for plain alphanumeric input)
"""
import re
from dataclasses import dataclass, field

from .gs1 import parse_gs1, GS1ParseResult


@dataclass
class BarcodeParseResult:
    """Complete result of barcode detection and parsing."""
    raw_input: str = ""
    normalized_input: str = ""
    barcode_type: str = "unknown"  # gs1, ean, serial, hu, unknown
    manufacturing_part_number: str = ""
    ean_code: str = ""
    serial_number: str = ""
    gs1_result: GS1ParseResult | None = None
    warnings: list = field(default_factory=list)
    error: str = ""


def normalize_input(raw: str) -> str:
    """
    Normalize raw scanner input:
    - strip whitespace, CR, LF
    - remove common scanner suffix/prefix noise
    - uppercase
    """
    cleaned = raw.strip().replace("\r", "").replace("\n", "").replace("\t", "")
    # Remove null bytes and other control chars except GS (0x1D) which is used by GS1
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1c\x1e-\x1f]", "", cleaned)
    return cleaned


def is_ean13(value: str) -> bool:
    """Check if value is a valid EAN-13 (13 digits with valid check digit)."""
    if not re.match(r"^\d{13}$", value):
        return False
    # Verify EAN-13 check digit
    digits = [int(d) for d in value]
    checksum = sum(d * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits[:12]))
    expected_check = (10 - (checksum % 10)) % 10
    return digits[12] == expected_check


def is_hu_barcode(value: str) -> bool:
    """
    Detect if input looks like an HU barcode.
    HU barcodes typically start with 'HU' or are numeric 18-20 digit SSCC codes.
    """
    upper = value.upper()
    if upper.startswith("HU"):
        return True
    # SSCC-18 format (18 digits)
    if re.match(r"^\d{18,20}$", value):
        return True
    return False


def detect_and_parse(raw_input: str) -> BarcodeParseResult:
    """
    Detect barcode type and parse content from raw scanner input.

    Priority:
    1. GS1 DataMatrix (if ]2d prefix present)
    2. HU barcode
    3. EAN-13 (exactly 13 digits with valid check digit)
    4. Serial number (anything else)
    """
    result = BarcodeParseResult(raw_input=raw_input)
    normalized = normalize_input(raw_input)
    result.normalized_input = normalized

    if not normalized:
        result.barcode_type = "unknown"
        result.error = "Empty scan input"
        return result

    # 1. Try GS1 DataMatrix
    if normalized.startswith("]2d") or normalized.startswith("]2D"):
        gs1 = parse_gs1(normalized)
        result.gs1_result = gs1
        if gs1.is_gs1:
            result.barcode_type = "gs1"
            result.manufacturing_part_number = gs1.manufacturing_part_number
            result.serial_number = gs1.serial_number
            result.warnings = gs1.warnings
            if gs1.error:
                result.error = gs1.error
            return result

    # 2. Check for HU barcode
    if is_hu_barcode(normalized):
        result.barcode_type = "hu"
        return result

    # 3. Check for EAN-13
    if is_ean13(normalized):
        result.barcode_type = "ean"
        result.ean_code = normalized
        return result

    # 4. Default: treat as serial number
    result.barcode_type = "serial"
    result.serial_number = normalized
    return result
