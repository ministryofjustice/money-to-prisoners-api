# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0011_auto_20150902_1630'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='transaction',
            name='upload_counter',
        ),
    ]
