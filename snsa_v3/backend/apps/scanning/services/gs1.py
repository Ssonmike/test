from dataclasses import dataclass, field


# GS1 Application Identifiers we care about
# Format: (AI code, name, fixed_length or None for variable)
AI_DEFS = {
    "240": ("manufacturing_part_number", None, 30),  # variable, max 30
    "21": ("serial_number", None, 20),               # variable, max 20
    "01": ("gtin", 14, 14),                           # fixed 14
    "10": ("batch", None, 20),                        # variable, max 20
    "37": ("quantity", None, 8),                      # variable, max 8
}

# Group separator character (FNC1 encoded by scanner as GS)
GS_CHAR = "\x1d"

# Scanner prefix for GS1 DataMatrix
GS1_PREFIX = "]2d"
GS1_PREFIX_UPPER = "]2D"


@dataclass
class GS1ParseResult:
    """Result of parsing a GS1 DataMatrix barcode."""
    raw_input: str = ""
    is_gs1: bool = False
    manufacturing_part_number: str = ""
    serial_number: str = ""
    gtin: str = ""
    batch: str = ""
    quantity: str = ""
    ai_map: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    error: str = ""


def strip_gs1_prefix(raw: str) -> tuple[str, bool]:
    """Remove ]2d or ]2D prefix, return (stripped, was_gs1)."""
    if raw.startswith(GS1_PREFIX) or raw.startswith(GS1_PREFIX_UPPER):
        return raw[3:], True
    return raw, False


def parse_gs1(raw_input: str) -> GS1ParseResult:

    result = GS1ParseResult(raw_input=raw_input)

    body, is_gs1 = strip_gs1_prefix(raw_input.strip())
    if not is_gs1:
        result.is_gs1 = False
        return result

    result.is_gs1 = True

    # Parse AI segments
    pos = 0
    while pos < len(body):
        matched = False

        # Try matching known AIs (longer codes first to avoid ambiguity)
        for ai_code in sorted(AI_DEFS.keys(), key=len, reverse=True):
            if body[pos:].startswith(ai_code):
                field_name, fixed_len, max_len = AI_DEFS[ai_code]
                pos += len(ai_code)

                if fixed_len:
                    # Fixed-length field
                    value = body[pos:pos + fixed_len]
                    pos += fixed_len
                else:
                    # Variable-length: read until GS separator or end
                    end = body.find(GS_CHAR, pos)
                    if end == -1:
                        value = body[pos:]
                        pos = len(body)
                    else:
                        value = body[pos:end]
                        pos = end + 1  # skip GS

                value = value.strip()
                if len(value) > max_len:
                    result.warnings.append(
                        f"AI({ai_code}) value exceeds max length {max_len}: {len(value)}"
                    )

                result.ai_map[ai_code] = value
                setattr(result, field_name, value)
                matched = True
                break

        if not matched:
            # Skip unknown content until next GS or end
            end = body.find(GS_CHAR, pos)
            if end == -1:
                unknown = body[pos:]
                result.warnings.append(f"Unknown AI content at pos {pos}: {unknown[:20]}")
                break
            else:
                unknown = body[pos:end]
                result.warnings.append(f"Unknown AI content at pos {pos}: {unknown[:20]}")
                pos = end + 1

    # Validation
    if not result.manufacturing_part_number and not result.serial_number:
        result.error = "GS1 barcode contains neither AI(240) nor AI(21)"

    return result
