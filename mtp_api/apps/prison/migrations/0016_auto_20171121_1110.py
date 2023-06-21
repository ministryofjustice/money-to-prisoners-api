# Generated by Django 1.10.7 on 2017-11-21 11:10
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('prison', '0015_single_offender_id'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='prisonerlocation',
            options={'get_latest_by': 'created', 'ordering': ('prisoner_number',), 'permissions': (('view_prisonerlocation', 'Can view prisoner location'),)},
        ),
    ]
