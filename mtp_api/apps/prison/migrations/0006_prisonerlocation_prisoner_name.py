# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('prison', '0005_prison_general_ledger_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='prisonerlocation',
            name='prisoner_name',
            field=models.CharField(max_length=250, blank=True),
        ),
    ]
