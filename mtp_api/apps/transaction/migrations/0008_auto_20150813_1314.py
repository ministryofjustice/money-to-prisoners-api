# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0007_auto_20150813_1251'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='transaction',
            index_together=set([('prisoner_number', 'prisoner_dob')]),
        ),
    ]
