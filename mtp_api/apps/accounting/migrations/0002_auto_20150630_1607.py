# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import model_utils.fields
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0003_auto_20150630_1607'),
        ('accounting', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Log',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, serialize=False, auto_created=True)),
                ('created', model_utils.fields.AutoCreatedField(verbose_name='created', editable=False, default=django.utils.timezone.now)),
                ('modified', model_utils.fields.AutoLastModifiedField(verbose_name='modified', editable=False, default=django.utils.timezone.now)),
                ('transaction', models.ForeignKey(to='transaction.Transaction')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.RemoveField(
            model_name='accountingbatch',
            name='locked_by',
        ),
        migrations.RemoveField(
            model_name='accountingbatch',
            name='transaction',
        ),
        migrations.DeleteModel(
            name='AccountingBatch',
        ),
    ]
