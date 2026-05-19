from django.contrib import admin
from django.utils.html import format_html
from .models import ACFInteractionLog


@admin.register(ACFInteractionLog)
class ACFInteractionLogAdmin(admin.ModelAdmin):
    list_display = [
        "created_at",
        "direction_badge",
        "hu_number",
        "session_link",
        "status_badge",
        "http_status",
        "duration_ms",
    ]
    list_filter  = ["direction", "success", "http_status"]
    search_fields = ["hu_number", "error_message"]
    readonly_fields = [
        "created_at", "direction", "hu_number", "session",
        "success", "http_status", "duration_ms", "error_message",
        "request_payload_pretty", "response_payload_pretty",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"

    # No add or change permissions — this is a read-only log
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # ── Visual fields ─────────────────────────────────────────────────────────

    @admin.display(description="Type")
    def direction_badge(self, obj):
        color = "blue" if obj.direction == "lookup" else "purple"
        label = obj.get_direction_display()
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:4px; font-size:11px; font-weight:600">{}</span>',
            "#1d4ed8" if color == "blue" else "#7e22ce",
            label,
        )

    @admin.display(description="Result")
    def status_badge(self, obj):
        if obj.success:
            return format_html(
                '<span style="background:#16a34a; color:white; padding:2px 8px; '
                'border-radius:4px; font-size:11px; font-weight:600">OK</span>'
            )
        return format_html(
            '<span style="background:#dc2626; color:white; padding:2px 8px; '
            'border-radius:4px; font-size:11px; font-weight:600">FAIL</span>'
        )

    @admin.display(description="Session")
    def session_link(self, obj):
        if not obj.session_id:
            return "—"
        return format_html(
            '<a href="/admin/scanning/scansession/{}/change/">Session #{}</a>',
            obj.session_id,
            obj.session_id,
        )

    @admin.display(description="Request payload")
    def request_payload_pretty(self, obj):
        if not obj.request_payload:
            return "—"
        import json
        return format_html(
            '<pre style="font-size:12px; white-space:pre-wrap; word-break:break-all">{}</pre>',
            json.dumps(obj.request_payload, indent=2, ensure_ascii=False),
        )

    @admin.display(description="Response payload")
    def response_payload_pretty(self, obj):
        if not obj.response_payload:
            return "—"
        import json
        return format_html(
            '<pre style="font-size:12px; white-space:pre-wrap; word-break:break-all">{}</pre>',
            json.dumps(obj.response_payload, indent=2, ensure_ascii=False),
        )

    def get_fieldsets(self, request, obj=None):
        return [
            ("Identification", {
                "fields": ["created_at", "direction", "hu_number", "session"]
            }),
            ("Result", {
                "fields": ["success", "http_status", "duration_ms", "error_message"]
            }),
            ("Payloads", {
                "fields": ["request_payload_pretty", "response_payload_pretty"],
                "classes": ["collapse"],
            }),
        ]
