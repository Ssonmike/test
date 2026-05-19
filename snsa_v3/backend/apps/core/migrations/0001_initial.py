
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='SystemConfiguration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_timeout_minutes', models.PositiveIntegerField(default=30, help_text='Minutes of inactivity before a scan session expires.')),
                ('allow_duplicate_sn_across_sessions', models.BooleanField(default=False, help_text='If enabled, the same SN may appear across different sessions.')),
                ('enable_ip_whitelist', models.BooleanField(default=False, help_text='If enabled, only whitelisted IPs are allowed to access the application.')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'System Configuration',
                'verbose_name_plural': 'System Configuration',
            },
        ),
    ]
