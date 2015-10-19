# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0014_auto_20151013_1113'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='transaction',
            options={'permissions': (('view_transaction', 'Can view transaction'), ('view_bank_details_transaction', 'Can view bank details of transaction'), ('lock_transaction', 'Can lock transaction'), ('unlock_transaction', 'Can unlock transaction'), ('patch_credited_transaction', 'Can patch credited transaction'), ('patch_processed_transaction', 'Can patch processed transaction')), 'ordering': ('received_at',)},
        ),
    ]
