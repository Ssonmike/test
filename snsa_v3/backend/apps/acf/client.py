import logging
import time

import requests
from django.conf import settings

from .schemas import AcfHUResponse, AcfItem

logger = logging.getLogger("apps.acf")


class ACFError(Exception):
    """Error communicating with ACF."""
    pass


class ACFClient:
    """
    HTTP client for ACF service (SAP bridge).
    Logs every call to ACFInteractionLog (best-effort).
    """

    def __init__(self, session_id: int | None = None):
        self.base_url = settings.APIM_BASE_URL.rstrip("/")
        self.api_key = settings.APIM_API_KEY
        self.timeout = settings.APIM_TIMEOUT_SECONDS
        self.session_id = session_id

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }

    def _log(self, direction, hu_number, success, http_status, duration_ms,
             request_payload, response_payload, error_message=""):
        try:
            from .models import ACFInteractionLog
            ACFInteractionLog.objects.create(
                direction=direction, hu_number=hu_number, session_id=self.session_id,
                success=success, http_status=http_status, duration_ms=duration_ms,
                request_payload=request_payload, response_payload=response_payload,
                error_message=error_message,
            )
        except Exception as log_exc:
            logger.warning("ACFInteractionLog write failed: %s", log_exc)

    def get_hu(self, hu_number: str) -> AcfHUResponse:
        """Look up HU items via ACF. Raises ACFError on failure."""
        url = f"{self.base_url}/hu/{hu_number}"
        logger.info("ACF HU lookup → %s", url)

        t0 = time.monotonic()
        try:
            response = requests.get(url, headers=self._headers(), timeout=self.timeout)
        except requests.exceptions.ConnectionError as e:
            duration_ms = int((time.monotonic() - t0) * 1000)
            msg = f"ACF unavailable: {e}"
            self._log("lookup", hu_number, False, None, duration_ms,
                      {"hu_number": hu_number}, None, msg)
            raise ACFError(msg) from e
        except requests.exceptions.Timeout:
            duration_ms = int((time.monotonic() - t0) * 1000)
            msg = f"ACF timeout after {self.timeout}s"
            self._log("lookup", hu_number, False, None, duration_ms,
                      {"hu_number": hu_number}, None, msg)
            raise ACFError(msg)

        duration_ms = int((time.monotonic() - t0) * 1000)

        if response.status_code == 404:
            msg = f"HU not found in SAP: {hu_number}"
            self._log("lookup", hu_number, False, 404, duration_ms,
                      {"hu_number": hu_number}, _safe_json(response), msg)
            raise ACFError(msg)

        if not response.ok:
            msg = f"ACF responded {response.status_code}: {response.text[:200]}"
            self._log("lookup", hu_number, False, response.status_code, duration_ms,
                      {"hu_number": hu_number}, _safe_json(response), msg)
            raise ACFError(msg)

        data = response.json()
        items = [
            AcfItem(
                material=item["material"],
                description=item.get("description", ""),
                expected_qty=item["quantity"],
                sn_profile=item.get("snProfile", ""),
                is_serialised=item.get("isSerialized", bool(item.get("snProfile"))),
                batch=item.get("batch", ""),
                delivery_ref=item.get("deliveryRef", ""),
                manufacturing_part_number=item.get("manufacturingPartNumber", ""),
                ean_code=item.get("ean", ""),
                uom=item.get("uom", "EA"),
            )
            for item in data["items"]
        ]
        self._log("lookup", hu_number, True, response.status_code, duration_ms,
                  {"hu_number": hu_number}, data)
        logger.info("ACF HU %s → %d items (%dms)", hu_number, len(items), duration_ms)
        return AcfHUResponse(hu_number=data.get("huNumber", data.get("hu_number", hu_number)), items=items)

    def push_serials(self, payload: dict) -> dict:
        """Push confirmed serials to SAP via ACF. Raises ACFError on failure."""
        url = f"{self.base_url}/serials/push"
        hu_number = payload.get("huNumber", "")
        logger.info("ACF push → HU %s (%d items)", hu_number, len(payload.get("items", [])))

        t0 = time.monotonic()
        try:
            response = requests.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
        except requests.exceptions.ConnectionError as e:
            duration_ms = int((time.monotonic() - t0) * 1000)
            msg = f"ACF unavailable on push: {e}"
            self._log("push", hu_number, False, None, duration_ms, payload, None, msg)
            raise ACFError(msg) from e
        except requests.exceptions.Timeout:
            duration_ms = int((time.monotonic() - t0) * 1000)
            msg = f"ACF push timeout after {self.timeout}s"
            self._log("push", hu_number, False, None, duration_ms, payload, None, msg)
            raise ACFError(msg)

        duration_ms = int((time.monotonic() - t0) * 1000)

        if not response.ok:
            msg = f"ACF push responded {response.status_code}: {response.text[:200]}"
            self._log("push", hu_number, False, response.status_code, duration_ms,
                      payload, _safe_json(response), msg)
            raise ACFError(msg)

        result = response.json()
        self._log("push", hu_number, True, response.status_code, duration_ms, payload, result)
        logger.info("ACF push OK → SAP doc: %s (%dms)", result.get("sap_document_ref"), duration_ms)
        return result


def _safe_json(response):
    try:
        return response.json()
    except Exception:
        return {"raw": response.text[:500]} if response.text else None
