# Generated by Django 3.2.23 on 2023-11-21 14:34

from django.contrib.postgres import operations
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('credit', '0040_removed_single_offender_id_from_credit'),
    ]

    operations = [
        operations.AddIndexConcurrently(
            model_name='credit',
            index=models.Index(fields=['created'], name='credit_cred_created_18d594_idx'),
        )
    ]
