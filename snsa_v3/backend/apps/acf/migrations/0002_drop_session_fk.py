# Temporarily convert session FK to plain integer
# to allow scanning app to replace ScanSession model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("acf", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="acfinteractionlog",
            name="session",
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
