# Generated by Django 1.9.12 on 2017-01-17 13:35
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('prison', '0012_prison_names'),
    ]

    operations = [
        migrations.AlterField(
            model_name='prison',
            name='general_ledger_code',
            field=models.CharField(max_length=8),
        ),
    ]
