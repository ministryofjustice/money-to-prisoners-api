# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0005_auto_20150727_1610'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='transaction',
            options={'permissions': (('view_transaction', 'Can view transaction'), ('take_transaction', 'Can take transaction'), ('release_transaction', 'Can release transaction'), ('patch_credited_transaction', 'Can patch credited transaction')), 'ordering': ('received_at',)},
        ),
    ]
