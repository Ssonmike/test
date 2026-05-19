from rest_framework import serializers
from .models import ScanSession, HUContentItem, SerialNumberScan, SNProfile


class SNProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = SNProfile
        fields = ["id", "code", "name", "prefix_char", "expected_length", "is_active"]


class SerialNumberScanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SerialNumberScan
        fields = [
            "id", "raw_input", "normalized_input", "barcode_type",
            "scanned_serial", "scanned_ean", "scanned_manufacturing_part",
            "is_valid", "rejection_code", "rejection_reason",
            "matched_by", "scanned_at",
        ]


class HUContentItemSerializer(serializers.ModelSerializer):
    remaining_qty = serializers.ReadOnlyField()
    is_fully_scanned = serializers.ReadOnlyField()
    scans = serializers.SerializerMethodField()

    class Meta:
        model = HUContentItem
        fields = [
            "id", "material_number", "description",
            "expected_qty", "scanned_qty", "remaining_qty", "is_fully_scanned",
            "is_serialised", "sn_profile_code",
            "manufacturing_part_number", "ean_code", "batch", "uom",
            "delivery_ref", "sort_order", "last_scanned_at",
            "scans",
        ]

    def get_scans(self, obj):
        valid = obj.scans.filter(is_valid=True)
        return SerialNumberScanSerializer(valid, many=True).data

    def get_fields(self):
        fields = super().get_fields()
        # Only include scans in detail views, not lists
        if self.context.get("exclude_scans"):
            fields.pop("scans", None)
        return fields


class HUContentItemCompactSerializer(serializers.ModelSerializer):
    """Compact version without individual scans — for list/progress views."""
    remaining_qty = serializers.ReadOnlyField()
    is_fully_scanned = serializers.ReadOnlyField()

    class Meta:
        model = HUContentItem
        fields = [
            "id", "material_number", "description",
            "expected_qty", "scanned_qty", "remaining_qty", "is_fully_scanned",
            "is_serialised", "sn_profile_code",
            "manufacturing_part_number", "ean_code",
        ]


class ScanSessionSerializer(serializers.ModelSerializer):
    content_items = HUContentItemCompactSerializer(many=True, read_only=True)
    total_expected = serializers.ReadOnlyField()
    total_scanned = serializers.ReadOnlyField()
    is_all_scanned = serializers.ReadOnlyField()
    serialised_item_count = serializers.ReadOnlyField()

    class Meta:
        model = ScanSession
        fields = [
            "id", "hu_number", "flow_type", "status",
            "total_expected", "total_scanned", "is_all_scanned",
            "serialised_item_count",
            "last_scanned_item_display", "last_scanned_serial_display",
            "sap_document_ref", "sap_push_attempts", "failure_reason",
            "pending_item_id",
            "created_at", "last_activity_at", "completed_at",
            "content_items",
        ]


class ScanSessionDetailSerializer(ScanSessionSerializer):
    """Full session detail including individual scan records."""
    content_items = HUContentItemSerializer(many=True, read_only=True)


class HULookupSerializer(serializers.Serializer):
    hu_number = serializers.CharField(max_length=64)


class ScanInputSerializer(serializers.Serializer):
    scan_input = serializers.CharField(max_length=512)
    manual_item_id = serializers.IntegerField(required=False, allow_null=True, default=None)
