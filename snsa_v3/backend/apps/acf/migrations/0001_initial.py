import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('scanning', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ACFInteractionLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('direction', models.CharField(choices=[('lookup', 'HU Lookup'), ('push', 'Serial Push')], db_index=True, max_length=16)),
                ('hu_number', models.CharField(db_index=True, max_length=64)),
                ('success', models.BooleanField(db_index=True, default=False)),
                ('http_status', models.PositiveSmallIntegerField(blank=True, help_text='HTTP status code returned by ACF. Null if a connection error occurred.', null=True)),
                ('duration_ms', models.PositiveIntegerField(blank=True, help_text='Call duration in milliseconds.', null=True)),
                ('error_message', models.TextField(blank=True, default='', help_text='Error message when success=False.')),
                ('request_payload', models.JSONField(blank=True, help_text='Payload sent to ACF. For lookups (GET) it contains {hu_number}.', null=True)),
                ('response_payload', models.JSONField(blank=True, help_text='Response received from ACF. Null on connection error/timeout.', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('session', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='acf_logs', to='scanning.scansession')),
            ],
            options={
                'verbose_name': 'ACF Interaction Log',
                'verbose_name_plural': 'ACF Interaction Logs',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['direction', 'success'], name='acf_acfinte_directi_9b6776_idx'), models.Index(fields=['hu_number', 'created_at'], name='acf_acfinte_hu_numb_eb5189_idx')],
            },
        ),
    ]
