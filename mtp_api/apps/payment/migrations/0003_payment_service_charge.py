# -*- coding: utf-8 -*-
# Generated by Django 1.9.1 on 2016-02-12 17:02
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0002_auto_20160211_1459'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='service_charge',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
