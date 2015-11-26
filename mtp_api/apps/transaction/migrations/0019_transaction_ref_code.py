# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0018_transaction_category'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='ref_code',
            field=models.CharField(max_length=12, null=True),
        ),
    ]
