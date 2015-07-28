# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0004_log'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='transaction',
            options={'permissions': (('view_transaction', 'Can view transaction'),), 'ordering': ('received_at',)},
        ),
    ]
