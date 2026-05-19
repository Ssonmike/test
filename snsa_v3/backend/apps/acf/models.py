from django.db import models


class ACFInteractionLog(models.Model):
    """
    Log of every HTTP call between SNSA and the ACF service.

    Automatically created in ACFClient.get_hu() and push_serials().
    Provides full traceability for debugging, auditing and support.
    Does not block the main flow: if logging fails, the operation continues.
    """

    DIRECTION_LOOKUP = "lookup"
    DIRECTION_PUSH   = "push"
    DIRECTION_CHOICES = [
        (DIRECTION_LOOKUP, "HU Lookup"),
        (DIRECTION_PUSH,   "Serial Push"),
    ]

    # ── Identification ────────────────────────────────────────────────────────
    direction  = models.CharField(max_length=16, choices=DIRECTION_CHOICES, db_index=True)
    hu_number  = models.CharField(max_length=64, db_index=True)

    # FK nullable: the log is created before the session exists (during lookup),
    # and may survive if the session is deleted.
    session = models.ForeignKey(
        "scanning.ScanSession",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="acf_logs",
    )

    # ── Result ────────────────────────────────────────────────────────────────
    success     = models.BooleanField(default=False, db_index=True)
    http_status = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="HTTP status code returned by ACF. Null if a connection error occurred."
    )
    duration_ms = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Call duration in milliseconds."
    )
    error_message = models.TextField(
        blank=True, default="",
        help_text="Error message when success=False."
    )

    # ── Payloads ──────────────────────────────────────────────────────────────
    request_payload  = models.JSONField(
        null=True, blank=True,
        help_text="Payload sent to ACF. For lookups (GET) it contains {hu_number}."
    )
    response_payload = models.JSONField(
        null=True, blank=True,
        help_text="Response received from ACF. Null on connection error/timeout."
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ACF Interaction Log"
        verbose_name_plural = "ACF Interaction Logs"
        indexes = [
            models.Index(fields=["direction", "success"]),
            models.Index(fields=["hu_number", "created_at"]),
        ]

    def __str__(self):
        status = "OK" if self.success else "FAIL"
        return f"[{status}] {self.get_direction_display()} — {self.hu_number} ({self.created_at:%Y-%m-%d %H:%M})"
