# Generated by Django 1.9.4 on 2016-10-07 12:04
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0008_auto_20161006_1456'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='batch',
            options={'get_latest_by': 'date', 'ordering': ('date',), 'permissions': (('view_batch', 'Can view batch'),), 'verbose_name_plural': 'batches'},
        ),
    ]
