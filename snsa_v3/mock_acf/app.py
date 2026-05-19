"""
Mock ACF Service, simulates the ACF middleware bridge to SAP.

BCD-compliant test HUs:
  HU_SINGLE_GS1    → single SKU, GS1-capable monitor, qty 3
  HU_SINGLE_EAN    → single SKU, EAN-only monitor (no GS1), qty 2
  HU_MULTI         → multi SKU (2 monitors + 1 accessory), qty 2+1+1
  HU_NO_SERIAL     → exists but no serialization required
  HU_ACCESSORY     → single SKU, accessories (II02 profile), qty 2
  HU_USB           → single SKU, USB adapter (II03 profile), qty 1
  HU_AMBIGUOUS     → multi SKU, two items sharing same SN profile
  HU_ALREADY_DONE  → simulates already-serialized HU
  HU_FAIL          → simulates ACF internal error (502)
  HU_PUSH_FAIL     → lookup OK, but push fails (502)
  HU_DUP_REJECT    → push rejects duplicate serial

Extra visible business rule:
  For items with EAN-13, the last 5 digits before the check digit
  must match the first 5 digits of the serial number.

Example:
  EAN 4948570123889 -> expected serial prefix 12388
"""

from copy import deepcopy

from flask import Flask, jsonify, request

app = Flask(__name__)


def extract_serial_prefix_from_ean(ean_code: str) -> str:
    """
    The last 5 digits before the EAN check digit must match
    the first 5 digits of the serial number.
    """
    ean = (ean_code or "").strip()
    if len(ean) != 13 or not ean.isdigit():
        return ""
    return ean[-6:-1]


def serial_matches_ean_prefix(ean_code: str, serial_number: str) -> bool:
    prefix = extract_serial_prefix_from_ean(ean_code)
    serial = (serial_number or "").strip().upper()
    return bool(prefix and serial.startswith(prefix))


def build_sample_serials(sn_profile: str, ean_code: str) -> list[str]:
    prefix = extract_serial_prefix_from_ean(ean_code)
    if not prefix:
        return []

    if sn_profile == "II01":
        # Total length 13, starts with "1"
        # Example: 12388 + 8 more chars = 13
        return [
            f"{prefix}00000001",
            f"{prefix}00000002",
        ]

    if sn_profile == "II02":
        # Total length 13, starts with "0"
        # If your business confirms the EAN-prefix rule also applies here,
        # these samples remain useful. Adjust if needed.
        return [
            f"{prefix}00000001",
            f"{prefix}00000002",
        ]

    if sn_profile == "II03":
        # Total length 18, starts with "E"
        # For USB adapters the business rule may differ.
        # Keeping examples visible anyway if you want to test the mapping.
        return [
            f"{prefix}0000000000001",
        ]

    return []


def enrich_item(item: dict) -> dict:
    item = deepcopy(item)
    ean_code = item.get("ean", "")
    sn_profile = item.get("snProfile", "")

    serial_prefix = extract_serial_prefix_from_ean(ean_code)

    item["serialPrefixFromEan"] = serial_prefix
    item["eanSerialRule"] = (
        "last_5_digits_before_check_digit_of_ean_must_match_first_5_digits_of_serial"
        if serial_prefix
        else ""
    )
    item["sampleValidSerials"] = build_sample_serials(sn_profile, ean_code)

    return item


def enrich_hu_payload(hu_payload: dict) -> dict:
    payload = deepcopy(hu_payload)
    payload["items"] = [enrich_item(item) for item in payload.get("items", [])]
    return payload


# ─── Test HU Data ─────────────────────────────────────────────────────────────

HU_DATA = {
    "9780201379624": {
        "huNumber": "9780201379624",
        "items": [
            {
                "material": "PLB3272UHS",
                "description": "iiyama ProLite 32\" 4K Monitor",
                "quantity": 3,
                "snProfile": "II01",
                "isSerialized": True,
                "batch": "B2026001",
                "deliveryRef": "0080010001",
                "manufacturingPartNumber": "PLB3272UHS-B1",
                "ean": "4948570121830",
                "uom": "EA",
            }
        ],
    },
    "HU_SINGLE_EAN": {
        "huNumber": "HU_SINGLE_EAN",
        "items": [
            {
                "material": "PLB2483HSU",
                "description": "iiyama ProLite 24\" Monitor",
                "quantity": 2,
                "snProfile": "II01",
                "isSerialized": True,
                "batch": "B2026002",
                "deliveryRef": "0080010002",
                "manufacturingPartNumber": "",
                "ean": "4948570118458",
                "uom": "EA",
            }
        ],
    },
    "HU_MULTI": {
        "huNumber": "HU_MULTI",
        "items": [
            {
                "material": "PLB3272UHS",
                "description": "iiyama ProLite 32\" 4K Monitor",
                "quantity": 2,
                "snProfile": "II01",
                "isSerialized": True,
                "batch": "B2026003",
                "deliveryRef": "0080010003",
                "manufacturingPartNumber": "PLB3272UHS-B1",
                "ean": "4948570121830",
                "uom": "EA",
            },
            {
                "material": "ACC-WEBCAM-01",
                "description": "iiyama USB Webcam Accessory",
                "quantity": 1,
                "snProfile": "II02",
                "isSerialized": True,
                "batch": "B2026003",
                "deliveryRef": "0080010003",
                "manufacturingPartNumber": "ACC-WEBCAM-01-BK",
                "ean": "4948570118700",
                "uom": "EA",
            },
            {
                "material": "CABLE-HDMI-2M",
                "description": "HDMI Cable 2m (non-serialized)",
                "quantity": 4,
                "snProfile": "",
                "isSerialized": False,
                "batch": "B2026003",
                "deliveryRef": "0080010003",
                "manufacturingPartNumber": "",
                "ean": "4948570118800",
                "uom": "EA",
            },
        ],
    },
    "HU_NO_SERIAL": {
        "huNumber": "HU_NO_SERIAL",
        "items": [
            {
                "material": "CABLE-DP-1.5M",
                "description": "DisplayPort Cable 1.5m",
                "quantity": 10,
                "snProfile": "",
                "isSerialized": False,
                "batch": "B2026004",
                "deliveryRef": "0080010004",
                "manufacturingPartNumber": "",
                "ean": "4948570118900",
                "uom": "EA",
            },
            {
                "material": "MOUNT-DESK-01",
                "description": "Desk Mount Kit",
                "quantity": 5,
                "snProfile": "",
                "isSerialized": False,
                "batch": "B2026004",
                "deliveryRef": "0080010004",
                "manufacturingPartNumber": "",
                "ean": "4948570119000",
                "uom": "EA",
            },
        ],
    },
    "HU_ACCESSORY": {
        "huNumber": "HU_ACCESSORY",
        "items": [
            {
                "material": "ACC-STYLUS-02",
                "description": "iiyama Stylus Pen",
                "quantity": 2,
                "snProfile": "II02",
                "isSerialized": True,
                "batch": "B2026005",
                "deliveryRef": "0080010005",
                "manufacturingPartNumber": "ACC-STYLUS-02-SV",
                "ean": "4948570119100",
                "uom": "EA",
            }
        ],
    },
    "HU_USB": {
        "huNumber": "HU_USB",
        "items": [
            {
                "material": "USB-ADP-C01",
                "description": "iiyama USB-C Display Adapter",
                "quantity": 1,
                "snProfile": "II03",
                "isSerialized": True,
                "batch": "B2026006",
                "deliveryRef": "0080010006",
                "manufacturingPartNumber": "USB-ADP-C01-BK",
                "ean": "4948570119200",
                "uom": "EA",
            }
        ],
    },
    "HU_AMBIGUOUS": {
        "huNumber": "HU_AMBIGUOUS",
        "items": [
            {
                "material": "PLB2783QSU",
                "description": "iiyama ProLite 27\" Monitor A",
                "quantity": 1,
                "snProfile": "II01",
                "isSerialized": True,
                "batch": "B2026007",
                "deliveryRef": "0080010007",
                "manufacturingPartNumber": "PLB2783QSU-B1",
                "ean": "4948570119300",
                "uom": "EA",
            },
            {
                "material": "PLB2792QSU",
                "description": "iiyama ProLite 27\" Monitor B",
                "quantity": 1,
                "snProfile": "II01",
                "isSerialized": True,
                "batch": "B2026007",
                "deliveryRef": "0080010007",
                "manufacturingPartNumber": "PLB2792QSU-B1",
                "ean": "4948570119400",
                "uom": "EA",
            },
        ],
    },
    "HU_PUSH_FAIL": {
        "huNumber": "HU_PUSH_FAIL",
        "items": [
            {
                "material": "PLB3272UHS",
                "description": "iiyama ProLite 32\" 4K Monitor",
                "quantity": 1,
                "snProfile": "II01",
                "isSerialized": True,
                "batch": "B2026008",
                "deliveryRef": "0080010008",
                "manufacturingPartNumber": "PLB3272UHS-B1",
                "ean": "4948570121830",
                "uom": "EA",
            }
        ],
    },
    "HU_DUP_REJECT": {
        "huNumber": "HU_DUP_REJECT",
        "items": [
            {
                "material": "PLB3272UHS",
                "description": "iiyama ProLite 32\" 4K Monitor",
                "quantity": 1,
                "snProfile": "II01",
                "isSerialized": True,
                "batch": "B2026009",
                "deliveryRef": "0080010009",
                "manufacturingPartNumber": "PLB3272UHS-B1",
                "ean": "4948570121830",
                "uom": "EA",
            }
        ],
    },
}

SAP_DOC_COUNTER = {"value": 4900001000}

# Track pushed serials for duplicate detection
PUSHED_SERIALS = set()


@app.get("/hu/<hu_number>")
def hu_lookup(hu_number):
    hu_number = hu_number.strip().upper()

    if hu_number == "HU_FAIL":
        return jsonify({"error": "Simulated ACF internal error"}), 502

    if hu_number == "HU_ALREADY_DONE":
        return jsonify({"error": "HU already serialized in SAP"}), 409

    if hu_number not in HU_DATA:
        return jsonify({"error": f"HU not found: {hu_number}"}), 404

    return jsonify(enrich_hu_payload(HU_DATA[hu_number]))


@app.post("/serials/push")
def push_serials():
    payload = request.get_json(force=True)
    hu_number = payload.get("huNumber", "").strip().upper()

    if hu_number == "HU_PUSH_FAIL":
        return jsonify({"error": "Simulated SAP GR posting failure"}), 502

    items = payload.get("items", [])

    # Note: the EAN-derived serial prefix rule (last 5 before check digit = first 5 of serial)
    # is documented in the mock for reference and visible in lookup payloads, but it is NOT
    # enforced here as a hard push-time requirement. SNProfile validation (II01/II02/II03)
    # is the single source of truth for serial acceptance, and that runs in Django before push.
    # Check for duplicate serials (simulate SAP rejection)
    # Items now carry grouped serialNumbers list (camelCase) per Swagger contract
    for item in items:
        for sn in item.get("serialNumbers", []):
            sn = (sn or "").strip().upper()
            if hu_number == "HU_DUP_REJECT" and sn in PUSHED_SERIALS:
                return jsonify({
                    "error": f"Duplicate serial number rejected by SAP: {sn}",
                    "duplicate_serial": sn,
                    "code": "DUPLICATE_SERIAL_REJECTED",
                }), 422

    # Record serials as pushed
    for item in items:
        for sn in item.get("serialNumbers", []):
            sn = (sn or "").strip().upper()
            if sn:
                PUSHED_SERIALS.add(sn)

    SAP_DOC_COUNTER["value"] += 1
    sap_doc = str(SAP_DOC_COUNTER["value"])

    return jsonify({
        "status": "ok",
        "sap_document_ref": sap_doc,
        "huNumber": hu_number,
        "items_received": sum(len(i.get("serialNumbers", [])) for i in items),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
