# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import model_utils.fields
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('prison', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Transaction',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('created', model_utils.fields.AutoCreatedField(verbose_name='created', editable=False, default=django.utils.timezone.now)),
                ('modified', model_utils.fields.AutoLastModifiedField(verbose_name='modified', editable=False, default=django.utils.timezone.now)),
                ('upload_counter', models.PositiveIntegerField()),
                ('prisoner_number', models.CharField(blank=True, max_length=250)),
                ('prisoner_name', models.CharField(blank=True, max_length=250)),
                ('prisoner_dob', models.DateField(blank=True, null=True)),
                ('amount', models.PositiveIntegerField()),
                ('sender_bank_reference', models.CharField(blank=True, max_length=250)),
                ('sender_customer_reference', models.CharField(blank=True, max_length=250)),
                ('reference', models.TextField(blank=True)),
                ('received_at', models.DateTimeField()),
                ('prison', models.ForeignKey(blank=True, to='prison.Prison', null=True)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
