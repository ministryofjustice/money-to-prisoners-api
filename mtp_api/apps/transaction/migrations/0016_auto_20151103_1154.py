# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0015_auto_20151019_1430'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='transaction',
            name='reconciled',
        ),
        migrations.AlterField(
            model_name='log',
            name='action',
            field=models.CharField(max_length=50, choices=[('created', 'Created'), ('locked', 'Locked'), ('unlocked', 'Unlocked'), ('credited', 'Credited'), ('uncredited', 'Uncredited'), ('refunded', 'Refunded')]),
        ),
    ]
