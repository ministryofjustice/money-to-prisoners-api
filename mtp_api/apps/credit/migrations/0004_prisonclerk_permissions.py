# Generated by Django 1.9.4 on 2016-05-09 11:19
from django.db import migrations


def fix_prisonclerk_group_permissions(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('credit', '0003_auto_20160504_1502'),
    ]

    operations = [
        migrations.RunPython(fix_prisonclerk_group_permissions)
    ]
