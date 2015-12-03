# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0019_transaction_ref_code'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transaction',
            name='sender_name',
            field=models.CharField(max_length=250, blank=True),
        ),
    ]
