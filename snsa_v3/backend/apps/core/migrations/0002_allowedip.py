
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AllowedIP',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.GenericIPAddressField(help_text='Exact IPv4 or IPv6 address allowed to access the application.', unique=True)),
                ('description', models.CharField(blank=True, default='', help_text='Optional description identifying the origin of the IP.', max_length=255)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Allowed IP',
                'verbose_name_plural': 'Allowed IPs',
                'ordering': ['ip_address'],
            },
        ),
    ]
