# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0010_auto_20150827_0943'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='transaction',
            options={'permissions': (('view_transaction', 'Can view transaction'), ('view_bank_details_transaction', 'Can view bank details of transaction'), ('lock_transaction', 'Can lock transaction'), ('unlock_transaction', 'Can unlock transaction'), ('patch_credited_transaction', 'Can patch credited transaction'), ('patch_refunded_transaction', 'Can patch refunded transaction')), 'ordering': ('received_at',)},
        ),
        migrations.AddField(
            model_name='transaction',
            name='refunded',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='log',
            name='action',
            field=models.CharField(choices=[('created', 'Created'), ('locked', 'Locked'), ('unlocked', 'Unlocked'), ('credited', 'Credited'), ('uncredited', 'Uncredited'), ('refunded', 'Refunded')], max_length=50),
        ),
    ]
