from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class SNProfile(models.Model):
    """
    Serial number profile defining validation rules for a product category.
    Seeded from SAP master data.
    """
    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=128)
    prefix_char = models.CharField(max_length=4, help_text="Expected first character(s).")
    expected_length = models.PositiveIntegerField(help_text="Expected total length.")
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "SN Profile"
        verbose_name_plural = "SN Profiles"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} ({self.prefix_char}, len={self.expected_length})"

    def validate_serial(self, serial: str) -> tuple[bool, str | None]:
        if len(serial) != self.expected_length:
            return False, "SN_LENGTH_MISMATCH"
        if not serial.startswith(self.prefix_char):
            return False, "SN_PREFIX_MISMATCH"
        return True, None


class ScanSession(models.Model):
    """
    A scanning session for one Handling Unit.
    Full lifecycle state machine for BCD serial number scanning.
    """
    # Statuses
    STATUS_PENDING_LOOKUP = "pending_lookup"
    STATUS_READY_TO_SCAN = "ready_to_scan"
    STATUS_SCAN_IN_PROGRESS = "scan_in_progress"
    STATUS_READY_TO_COMPLETE = "ready_to_complete"
    STATUS_SAP_PUSH_IN_PROGRESS = "sap_push_in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_SAP_PUSH_FAILED = "sap_push_failed"
    STATUS_ABANDONED = "abandoned"
    STATUS_ERROR_LOOKUP_FAILED = "error_lookup_failed"
    STATUS_NO_SERIALIZATION = "no_serialization_required"

    STATUS_CHOICES = [
        (STATUS_PENDING_LOOKUP, "Pending Lookup"),
        (STATUS_READY_TO_SCAN, "Ready to Scan"),
        (STATUS_SCAN_IN_PROGRESS, "Scan In Progress"),
        (STATUS_READY_TO_COMPLETE, "Ready to Complete"),
        (STATUS_SAP_PUSH_IN_PROGRESS, "SAP Push In Progress"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_SAP_PUSH_FAILED, "SAP Push Failed"),
        (STATUS_ABANDONED, "Abandoned"),
        (STATUS_ERROR_LOOKUP_FAILED, "Error - Lookup Failed"),
        (STATUS_NO_SERIALIZATION, "No Serialization Required"),
    ]

    SCANNABLE_STATUSES = (STATUS_READY_TO_SCAN, STATUS_SCAN_IN_PROGRESS)
    COMPLETABLE_STATUSES = (STATUS_READY_TO_COMPLETE, STATUS_SAP_PUSH_FAILED)

    # Flow types
    FLOW_SINGLE_SKU = "single_sku"
    FLOW_MULTI_SKU = "multi_sku"
    FLOW_NO_SERIALIZATION = "no_serialization"
    FLOW_TYPE_CHOICES = [
        (FLOW_SINGLE_SKU, "Single SKU"),
        (FLOW_MULTI_SKU, "Multi SKU"),
        (FLOW_NO_SERIALIZATION, "No Serialization"),
    ]

    hu_number = models.CharField(max_length=64, db_index=True)
    flow_type = models.CharField(max_length=32, choices=FLOW_TYPE_CHOICES, default=FLOW_SINGLE_SKU)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING_LOOKUP)
    operator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="scan_sessions"
    )
    device_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # SAP push
    sap_push_attempts = models.PositiveIntegerField(default=0)
    sap_document_ref = models.CharField(max_length=64, blank=True, default="")
    failure_reason = models.TextField(blank=True, default="")

    # Recovery
    is_recovered = models.BooleanField(default=False)
    parent_session = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="child_sessions"
    )

    # Display
    last_scanned_item_display = models.CharField(max_length=128, blank=True, default="")
    last_scanned_serial_display = models.CharField(max_length=128, blank=True, default="")

    # Pending item context for EAN-first two-step flow
    pending_item_id = models.PositiveIntegerField(null=True, blank=True)
    pending_item_set_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["hu_number", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"Session({self.id}, HU={self.hu_number}, {self.status})"

    @property
    def total_expected(self):
        return sum(i.expected_qty for i in self.content_items.filter(is_serialised=True))

    @property
    def total_scanned(self):
        return sum(i.scanned_qty for i in self.content_items.filter(is_serialised=True))

    @property
    def is_all_scanned(self):
        items = self.content_items.filter(is_serialised=True)
        return items.exists() and all(i.is_fully_scanned for i in items)

    @property
    def serialised_item_count(self):
        return self.content_items.filter(is_serialised=True).count()

    def clear_pending_item(self):
        self.pending_item_id = None
        self.pending_item_set_at = None
        self.save(update_fields=["pending_item_id", "pending_item_set_at"])

    def set_pending_item(self, item_id: int):
        self.pending_item_id = item_id
        self.pending_item_set_at = timezone.now()
        self.save(update_fields=["pending_item_id", "pending_item_set_at"])


class HUContentItem(models.Model):
    """
    Immutable SAP snapshot for one HU line. Represents one material/SKU.
    """
    session = models.ForeignKey(ScanSession, on_delete=models.CASCADE, related_name="content_items")
    material_number = models.CharField(max_length=64)
    description = models.CharField(max_length=255, blank=True, default="")
    expected_qty = models.PositiveIntegerField()
    scanned_qty = models.PositiveIntegerField(default=0)
    is_serialised = models.BooleanField(default=False)
    sn_profile_code = models.CharField(max_length=32, blank=True, default="")
    sn_profile = models.ForeignKey(
        SNProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="content_items"
    )
    batch = models.CharField(max_length=64, blank=True, default="")
    delivery_ref = models.CharField(max_length=64, blank=True, default="")
    manufacturing_part_number = models.CharField(max_length=128, blank=True, default="")
    ean_code = models.CharField(max_length=64, blank=True, default="")
    uom = models.CharField(max_length=16, blank=True, default="EA")
    sort_order = models.PositiveIntegerField(default=0)
    last_scanned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sort_order", "id"]
        indexes = [
            models.Index(fields=["session", "is_serialised"]),
            models.Index(fields=["ean_code"]),
            models.Index(fields=["manufacturing_part_number"]),
        ]

    def __str__(self):
        return f"{self.material_number} ({self.scanned_qty}/{self.expected_qty})"

    @property
    def remaining_qty(self):
        return max(0, self.expected_qty - self.scanned_qty)

    @property
    def is_fully_scanned(self):
        return self.scanned_qty >= self.expected_qty


class SerialNumberScan(models.Model):
    """
    Records ALL scan attempts — valid and invalid.
    Only valid scans contribute to counters and SAP payload.
    """
    BARCODE_TYPE_CHOICES = [
        ("gs1", "GS1 DataMatrix"), ("ean", "EAN-13"),
        ("serial", "Serial Number"), ("hu", "HU Barcode"), ("unknown", "Unknown"),
    ]
    MATCHED_BY_CHOICES = [
        ("gs1", "GS1 (item + serial)"), ("ean_then_serial", "EAN then Serial"),
        ("serial_only", "Serial Only"), ("pending_context", "Pending Item Context"),
        ("manual_fallback", "Manual SKU Selection"), ("none", "No Match"),
    ]

    session = models.ForeignKey(ScanSession, on_delete=models.CASCADE, related_name="scans")
    content_item = models.ForeignKey(
        HUContentItem, on_delete=models.CASCADE, null=True, blank=True, related_name="scans"
    )
    raw_input = models.CharField(max_length=512)
    normalized_input = models.CharField(max_length=512, blank=True, default="")
    barcode_type = models.CharField(max_length=16, choices=BARCODE_TYPE_CHOICES, default="unknown")
    scanned_ean = models.CharField(max_length=64, blank=True, default="")
    scanned_manufacturing_part = models.CharField(max_length=128, blank=True, default="")
    scanned_serial = models.CharField(max_length=128, blank=True, default="", db_index=True)
    is_valid = models.BooleanField(default=False)
    rejection_reason = models.CharField(max_length=255, blank=True, default="")
    rejection_code = models.CharField(max_length=64, blank=True, default="")
    scanned_at = models.DateTimeField(auto_now_add=True)
    device_ip = models.GenericIPAddressField(null=True, blank=True)
    matched_by = models.CharField(max_length=32, choices=MATCHED_BY_CHOICES, default="none")
    duplicate_scope = models.CharField(max_length=16, blank=True, default="none")
    client_sequence = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-scanned_at"]
        indexes = [
            models.Index(fields=["session", "is_valid"]),
            models.Index(fields=["scanned_serial"]),
        ]

    def __str__(self):
        status = "OK" if self.is_valid else f"REJECTED({self.rejection_code})"
        return f"Scan({self.raw_input[:30]}, {status})"


class ScanLog(models.Model):
    """Immutable audit/event trail."""
    EVENT_TYPES = [
        ("session_created", "Session Created"), ("hu_lookup_ok", "HU Lookup OK"),
        ("hu_lookup_failed", "HU Lookup Failed"), ("scan_accepted", "Scan Accepted"),
        ("scan_rejected", "Scan Rejected"), ("item_completed", "Item Completed"),
        ("session_ready", "Session Ready to Complete"),
        ("sap_push_started", "SAP Push Started"), ("sap_push_ok", "SAP Push OK"),
        ("sap_push_failed", "SAP Push Failed"), ("session_abandoned", "Session Abandoned"),
        ("session_recovered", "Session Recovered"), ("status_change", "Status Change"),
    ]

    session = models.ForeignKey(ScanSession, on_delete=models.CASCADE, related_name="logs")
    event_type = models.CharField(max_length=32, choices=EVENT_TYPES, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    detail = models.JSONField(default=dict, blank=True)
    device_ip = models.GenericIPAddressField(null=True, blank=True)
    operator_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["session", "event_type"])]

    def __str__(self):
        return f"[{self.event_type}] Session {self.session_id}"
