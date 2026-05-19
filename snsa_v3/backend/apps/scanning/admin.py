from django.contrib import admin
from django.utils.html import format_html
from .models import SNProfile, ScanSession, HUContentItem, SerialNumberScan, ScanLog


# ─── SNProfile ────────────────────────────────────────────────────────────────

@admin.register(SNProfile)
class SNProfileAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "prefix_char", "expected_length", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["code", "name"]
    ordering = ["code"]


# ─── HUContentItem (inline) ──────────────────────────────────────────────────

class HUContentItemInline(admin.TabularInline):
    model = HUContentItem
    extra = 0
    fields = [
        "material_number", "description", "expected_qty", "scanned_qty",
        "is_serialised", "sn_profile_code", "manufacturing_part_number",
        "ean_code", "batch",
    ]
    readonly_fields = ["scanned_qty"]
    show_change_link = True


# ─── SerialNumberScan (inline for content item) ──────────────────────────────

class SerialNumberScanInline(admin.TabularInline):
    model = SerialNumberScan
    extra = 0
    fields = [
        "scanned_serial", "barcode_type", "is_valid", "rejection_code",
        "matched_by", "scanned_at",
    ]
    readonly_fields = [
        "scanned_serial", "barcode_type", "is_valid", "rejection_code",
        "matched_by", "scanned_at",
    ]

    def has_add_permission(self, request, obj=None):
        return False


# ─── ScanSession ──────────────────────────────────────────────────────────────

@admin.register(ScanSession)
class ScanSessionAdmin(admin.ModelAdmin):
    list_display = [
        "id", "hu_number", "flow_type_badge", "status_badge",
        "progress_display", "operator_name", "created_at",
    ]
    list_filter = ["status", "flow_type"]
    search_fields = ["hu_number", "sap_document_ref"]
    readonly_fields = [
        "created_at", "last_activity_at", "completed_at",
        "sap_document_ref", "sap_push_attempts",
        "last_scanned_item_display", "last_scanned_serial_display",
    ]
    inlines = [HUContentItemInline]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"

    @admin.display(description="Flow")
    def flow_type_badge(self, obj):
        colors = {
            "single_sku": ("#1d4ed8", "Single"),
            "multi_sku": ("#7e22ce", "Multi"),
            "no_serialization": ("#6b7280", "No SN"),
        }
        bg, label = colors.get(obj.flow_type, ("#6b7280", obj.flow_type))
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:4px; font-size:11px; font-weight:600">{}</span>',
            bg, label,
        )

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            "completed": "#16a34a",
            "scan_in_progress": "#2563eb",
            "ready_to_scan": "#ca8a04",
            "ready_to_complete": "#059669",
            "sap_push_failed": "#dc2626",
            "error_lookup_failed": "#dc2626",
            "abandoned": "#6b7280",
            "no_serialization_required": "#6b7280",
        }
        bg = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:4px; font-size:11px; font-weight:600">{}</span>',
            bg, obj.get_status_display(),
        )

    @admin.display(description="Progress")
    def progress_display(self, obj):
        return f"{obj.total_scanned}/{obj.total_expected}"

    @admin.display(description="Operator")
    def operator_name(self, obj):
        return obj.operator.username if obj.operator else "—"

    def get_fieldsets(self, request, obj=None):
        return [
            ("Session", {
                "fields": [
                    "hu_number", "flow_type", "status", "operator", "device_ip",
                ]
            }),
            ("Timestamps", {
                "fields": ["created_at", "last_activity_at", "completed_at"],
            }),
            ("SAP Push", {
                "fields": [
                    "sap_document_ref", "sap_push_attempts", "failure_reason",
                ],
            }),
            ("Display", {
                "fields": [
                    "last_scanned_item_display", "last_scanned_serial_display",
                    "pending_item_id",
                ],
                "classes": ["collapse"],
            }),
            ("Recovery", {
                "fields": ["is_recovered", "parent_session"],
                "classes": ["collapse"],
            }),
        ]


# ─── HUContentItem ───────────────────────────────────────────────────────────

@admin.register(HUContentItem)
class HUContentItemAdmin(admin.ModelAdmin):
    list_display = [
        "id", "session_link", "material_number", "expected_qty",
        "scanned_qty", "is_serialised", "is_fully_scanned",
    ]
    list_filter = ["is_serialised", "session__status"]
    search_fields = ["material_number", "ean_code", "manufacturing_part_number", "session__hu_number"]
    readonly_fields = ["scanned_qty", "last_scanned_at"]
    inlines = [SerialNumberScanInline]

    @admin.display(description="Session")
    def session_link(self, obj):
        return format_html(
            '<a href="/admin/scanning/scansession/{}/change/">Session #{} ({})</a>',
            obj.session_id, obj.session_id, obj.session.hu_number,
        )


# ─── SerialNumberScan ────────────────────────────────────────────────────────

@admin.register(SerialNumberScan)
class SerialNumberScanAdmin(admin.ModelAdmin):
    list_display = [
        "id", "session_hu", "scanned_serial", "barcode_type",
        "is_valid_badge", "rejection_code", "matched_by", "scanned_at",
    ]
    list_filter = ["is_valid", "barcode_type", "rejection_code", "matched_by"]
    search_fields = ["scanned_serial", "raw_input", "session__hu_number"]
    readonly_fields = [
        "session", "content_item", "raw_input", "normalized_input",
        "barcode_type", "scanned_serial", "scanned_ean",
        "scanned_manufacturing_part", "is_valid", "rejection_code",
        "rejection_reason", "matched_by", "duplicate_scope",
        "scanned_at", "device_ip",
    ]
    ordering = ["-scanned_at"]
    date_hierarchy = "scanned_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="HU")
    def session_hu(self, obj):
        return obj.session.hu_number

    @admin.display(description="Valid")
    def is_valid_badge(self, obj):
        if obj.is_valid:
            return format_html(
                '<span style="background:#16a34a; color:white; padding:2px 8px; '
                'border-radius:4px; font-size:11px">OK</span>'
            )
        return format_html(
            '<span style="background:#dc2626; color:white; padding:2px 8px; '
            'border-radius:4px; font-size:11px">REJECTED</span>'
        )


# ─── ScanLog ─────────────────────────────────────────────────────────────────

@admin.register(ScanLog)
class ScanLogAdmin(admin.ModelAdmin):
    list_display = ["id", "session_hu", "event_type", "timestamp", "detail_summary"]
    list_filter = ["event_type"]
    search_fields = ["session__hu_number"]
    readonly_fields = [
        "session", "event_type", "timestamp", "detail",
        "device_ip", "operator_id",
    ]
    ordering = ["-timestamp"]
    date_hierarchy = "timestamp"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="HU")
    def session_hu(self, obj):
        return obj.session.hu_number

    @admin.display(description="Detail")
    def detail_summary(self, obj):
        if not obj.detail:
            return "—"
        import json
        text = json.dumps(obj.detail, ensure_ascii=False)
        if len(text) > 80:
            text = text[:80] + "…"
        return text
