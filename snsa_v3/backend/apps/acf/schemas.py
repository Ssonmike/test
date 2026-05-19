from dataclasses import dataclass
from typing import List


@dataclass
class AcfItem:
    """An item/material within an HU — full BCD field set."""
    material: str
    description: str
    expected_qty: int
    sn_profile: str = ""
    is_serialised: bool = False
    batch: str = ""
    delivery_ref: str = ""
    manufacturing_part_number: str = ""
    ean_code: str = ""
    uom: str = "EA"


@dataclass
class AcfHUResponse:
    """Complete ACF response for an HU lookup."""
    hu_number: str
    items: List[AcfItem]


@dataclass
class AcfPushPayload:
    """Payload sent to ACF for SAP push."""
    hu_number: str
    session_id: int
    items: List[dict]
