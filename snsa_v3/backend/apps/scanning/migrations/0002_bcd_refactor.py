# Generated migration for BCD refactor
# Replaces old ScanSession/ScanRequirement/SNScan with new BCD-compliant models

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_sn_profiles(apps, schema_editor):
    SNProfile = apps.get_model("scanning", "SNProfile")
    profiles = [
        {
            "code": "II01",
            "name": "Monitors",
            "prefix_char": "1",
            "expected_length": 13,
            "description": "iiyama monitors — first char '1', length 13",
        },
        {
            "code": "II02",
            "name": "Accessories",
            "prefix_char": "0",
            "expected_length": 13,
            "description": "iiyama accessories — first char '0', length 13",
        },
        {
            "code": "II03",
            "name": "USB Adapters",
            "prefix_char": "E",
            "expected_length": 18,
            "description": "iiyama USB adapters — first char 'E', length 18",
        },
    ]
    for p in profiles:
        SNProfile.objects.get_or_create(code=p["code"], defaults=p)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("scanning", "0001_initial"),
        ("acf", "0002_drop_session_fk"),
    ]

    operations = [
        # ── Remove old models ─────────────────────────────────────────
        migrations.DeleteModel(name="SNScan"),
        migrations.DeleteModel(name="ScanRequirement"),
        migrations.DeleteModel(name="ScanSession"),

        # ── SNProfile ─────────────────────────────────────────────────
        migrations.CreateModel(
            name="SNProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(db_index=True, max_length=32, unique=True)),
                ("name", models.CharField(max_length=128)),
                ("prefix_char", models.CharField(help_text="Expected first character(s).", max_length=4)),
                ("expected_length", models.PositiveIntegerField(help_text="Expected total length.")),
                ("description", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(default=True)),
                ("last_sync_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "SN Profile",
                "verbose_name_plural": "SN Profiles",
                "ordering": ["code"],
            },
        ),

        # ── ScanSession ──────────────────────────────────────────────
        migrations.CreateModel(
            name="ScanSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("hu_number", models.CharField(db_index=True, max_length=64)),
                (
                    "flow_type",
                    models.CharField(
                        choices=[
                            ("single_sku", "Single SKU"),
                            ("multi_sku", "Multi SKU"),
                            ("no_serialization", "No Serialization"),
                        ],
                        default="single_sku",
                        max_length=32,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending_lookup", "Pending Lookup"),
                            ("ready_to_scan", "Ready to Scan"),
                            ("scan_in_progress", "Scan In Progress"),
                            ("ready_to_complete", "Ready to Complete"),
                            ("sap_push_in_progress", "SAP Push In Progress"),
                            ("completed", "Completed"),
                            ("sap_push_failed", "SAP Push Failed"),
                            ("abandoned", "Abandoned"),
                            ("error_lookup_failed", "Error - Lookup Failed"),
                            ("no_serialization_required", "No Serialization Required"),
                        ],
                        default="pending_lookup",
                        max_length=32,
                    ),
                ),
                ("device_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_activity_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("sap_push_attempts", models.PositiveIntegerField(default=0)),
                ("sap_document_ref", models.CharField(blank=True, default="", max_length=64)),
                ("failure_reason", models.TextField(blank=True, default="")),
                ("is_recovered", models.BooleanField(default=False)),
                ("last_scanned_item_display", models.CharField(blank=True, default="", max_length=128)),
                ("last_scanned_serial_display", models.CharField(blank=True, default="", max_length=128)),
                (
                    "pending_item_id",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="HUContentItem ID for EAN-first two-step scan flow.",
                        null=True,
                    ),
                ),
                ("pending_item_set_at", models.DateTimeField(blank=True, null=True)),
                (
                    "operator",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="scan_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "parent_session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="child_sessions",
                        to="scanning.scansession",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="scansession",
            index=models.Index(fields=["hu_number", "status"], name="scanning_sc_hu_numb_idx"),
        ),
        migrations.AddIndex(
            model_name="scansession",
            index=models.Index(fields=["status", "created_at"], name="scanning_sc_status__idx"),
        ),

        # ── HUContentItem ────────────────────────────────────────────
        migrations.CreateModel(
            name="HUContentItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("material_number", models.CharField(max_length=64)),
                ("description", models.CharField(blank=True, default="", max_length=255)),
                ("expected_qty", models.PositiveIntegerField()),
                ("scanned_qty", models.PositiveIntegerField(default=0)),
                ("is_serialised", models.BooleanField(default=False)),
                ("sn_profile_code", models.CharField(blank=True, default="", max_length=32)),
                ("batch", models.CharField(blank=True, default="", max_length=64)),
                ("delivery_ref", models.CharField(blank=True, default="", max_length=64)),
                ("manufacturing_part_number", models.CharField(blank=True, default="", max_length=128)),
                ("ean_code", models.CharField(blank=True, default="", max_length=64)),
                ("uom", models.CharField(blank=True, default="EA", max_length=16)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("last_scanned_at", models.DateTimeField(blank=True, null=True)),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="content_items",
                        to="scanning.scansession",
                    ),
                ),
                (
                    "sn_profile",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="content_items",
                        to="scanning.snprofile",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="hucontentitem",
            index=models.Index(fields=["session", "is_serialised"], name="scanning_hu_session_ser_idx"),
        ),
        migrations.AddIndex(
            model_name="hucontentitem",
            index=models.Index(fields=["ean_code"], name="scanning_hu_ean_idx"),
        ),
        migrations.AddIndex(
            model_name="hucontentitem",
            index=models.Index(fields=["manufacturing_part_number"], name="scanning_hu_mfr_idx"),
        ),

        # ── SerialNumberScan ─────────────────────────────────────────
        migrations.CreateModel(
            name="SerialNumberScan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("raw_input", models.CharField(max_length=512)),
                ("normalized_input", models.CharField(blank=True, default="", max_length=512)),
                (
                    "barcode_type",
                    models.CharField(
                        choices=[
                            ("gs1", "GS1 DataMatrix"),
                            ("ean", "EAN-13"),
                            ("serial", "Serial Number"),
                            ("hu", "HU Barcode"),
                            ("unknown", "Unknown"),
                        ],
                        default="unknown",
                        max_length=16,
                    ),
                ),
                ("scanned_ean", models.CharField(blank=True, default="", max_length=64)),
                ("scanned_manufacturing_part", models.CharField(blank=True, default="", max_length=128)),
                ("scanned_serial", models.CharField(blank=True, db_index=True, default="", max_length=128)),
                ("is_valid", models.BooleanField(default=False)),
                ("rejection_reason", models.CharField(blank=True, default="", max_length=255)),
                ("rejection_code", models.CharField(blank=True, default="", max_length=64)),
                ("scanned_at", models.DateTimeField(auto_now_add=True)),
                ("device_ip", models.GenericIPAddressField(blank=True, null=True)),
                (
                    "matched_by",
                    models.CharField(
                        choices=[
                            ("gs1", "GS1 (item + serial)"),
                            ("ean_then_serial", "EAN then Serial"),
                            ("serial_only", "Serial Only"),
                            ("pending_context", "Pending Item Context"),
                            ("manual_fallback", "Manual SKU Selection"),
                            ("none", "No Match"),
                        ],
                        default="none",
                        max_length=32,
                    ),
                ),
                ("duplicate_scope", models.CharField(blank=True, default="none", help_text="none, local, sap", max_length=16)),
                ("client_sequence", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scans",
                        to="scanning.scansession",
                    ),
                ),
                (
                    "content_item",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scans",
                        to="scanning.hucontentitem",
                    ),
                ),
            ],
            options={
                "ordering": ["-scanned_at"],
            },
        ),
        migrations.AddIndex(
            model_name="serialnumberscan",
            index=models.Index(fields=["session", "is_valid"], name="scanning_sn_sess_valid_idx"),
        ),
        migrations.AddIndex(
            model_name="serialnumberscan",
            index=models.Index(fields=["scanned_serial"], name="scanning_sn_serial_idx"),
        ),

        # ── ScanLog ──────────────────────────────────────────────────
        migrations.CreateModel(
            name="ScanLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("session_created", "Session Created"),
                            ("hu_lookup_ok", "HU Lookup OK"),
                            ("hu_lookup_failed", "HU Lookup Failed"),
                            ("scan_accepted", "Scan Accepted"),
                            ("scan_rejected", "Scan Rejected"),
                            ("item_completed", "Item Completed"),
                            ("session_ready", "Session Ready to Complete"),
                            ("sap_push_started", "SAP Push Started"),
                            ("sap_push_ok", "SAP Push OK"),
                            ("sap_push_failed", "SAP Push Failed"),
                            ("session_abandoned", "Session Abandoned"),
                            ("session_recovered", "Session Recovered"),
                            ("status_change", "Status Change"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("detail", models.JSONField(blank=True, default=dict)),
                ("device_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("operator_id", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="logs",
                        to="scanning.scansession",
                    ),
                ),
            ],
            options={
                "ordering": ["-timestamp"],
            },
        ),
        migrations.AddIndex(
            model_name="scanlog",
            index=models.Index(fields=["session", "event_type"], name="scanning_log_sess_evt_idx"),
        ),

        # ── Seed SN Profiles ─────────────────────────────────────────
        migrations.RunPython(
            seed_sn_profiles,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
