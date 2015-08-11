# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('prison', '0002_prisonerlocation'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='prisonerlocation',
            name='upload_counter',
        ),
    ]
