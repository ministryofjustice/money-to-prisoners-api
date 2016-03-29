# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0016_auto_20151103_1154'),
        ('account', '0002_auto_20151102_1143'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='file',
            new_name='batch'
        ),
        migrations.AlterField(
            model_name='batch',
            name='file_type',
            field=models.CharField(max_length=15, db_index=True),
        ),
        migrations.RenameField(
            model_name='batch',
            old_name='file_type',
            new_name='label'
        ),
        migrations.DeleteModel(
            name='FileType',
        ),
        migrations.RenameField(
            model_name='balance',
            old_name='file',
            new_name='batch'
        ),
        migrations.AlterField(
            model_name='balance',
            name='batch',
            field=models.OneToOneField(to='account.Batch', on_delete=models.CASCADE),
        ),
    ]
