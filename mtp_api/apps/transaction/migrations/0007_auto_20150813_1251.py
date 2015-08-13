# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0006_auto_20150807_1554'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='transaction',
            name='sender_bank_reference',
        ),
        migrations.RemoveField(
            model_name='transaction',
            name='sender_customer_reference',
        ),
        migrations.AddField(
            model_name='transaction',
            name='sender_account_number',
            field=models.CharField(default='unknown', max_length=50),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='transaction',
            name='sender_name',
            field=models.CharField(default='unknown', max_length=250),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='transaction',
            name='sender_roll_number',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='transaction',
            name='sender_sort_code',
            field=models.CharField(default='unknown', max_length=50),
            preserve_default=False,
        ),
    ]
