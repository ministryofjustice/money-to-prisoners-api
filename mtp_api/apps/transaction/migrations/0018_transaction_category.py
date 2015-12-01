# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0017_auto_20151125_1040'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='category',
            field=models.CharField(choices=[('debit', 'Debit'), ('credit', 'Credit')], default='CREDIT', max_length=50),
            preserve_default=False,
        ),
    ]
