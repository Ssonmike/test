

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ScanSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('hu_number', models.CharField(db_index=True, max_length=64)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('requirements_loaded', 'Requirements Loaded'), ('in_progress', 'In Progress'), ('complete', 'Complete'), ('sap_confirmed', 'SAP Confirmed'), ('sap_push_failed', 'SAP Push Failed'), ('error', 'Error')], default='pending', max_length=32)),
                ('error_message', models.TextField(blank=True, default='')),
                ('sap_document_ref', models.CharField(blank=True, default='', max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('operator', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='scan_sessions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ScanRequirement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('material', models.CharField(max_length=64)),
                ('description', models.CharField(blank=True, default='', max_length=128)),
                ('expected_qty', models.PositiveIntegerField()),
                ('scanned_qty', models.PositiveIntegerField(default=0)),
                ('sn_profile', models.CharField(blank=True, default='', max_length=32)),
                ('batch', models.CharField(blank=True, default='', max_length=32)),
                ('delivery_ref', models.CharField(blank=True, default='', max_length=64)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='requirements', to='scanning.scansession')),
            ],
        ),
        migrations.CreateModel(
            name='SNScan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('serial_number', models.CharField(db_index=True, max_length=128)),
                ('scanned_at', models.DateTimeField(auto_now_add=True)),
                ('requirement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='scans', to='scanning.scanrequirement')),
            ],
            options={
                'unique_together': {('requirement', 'serial_number')},
            },
        ),
    ]
