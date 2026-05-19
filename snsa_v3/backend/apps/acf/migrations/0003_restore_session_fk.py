# Restore session FK to point to the new ScanSession model

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("acf", "0002_drop_session_fk"),
        ("scanning", "0002_bcd_refactor"),
    ]

    operations = [
        migrations.AlterField(
            model_name="acfinteractionlog",
            name="session",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="acf_logs",
                to="scanning.scansession",
            ),
        ),
    ]
