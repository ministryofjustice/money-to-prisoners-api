# Generated by Django 1.9.4 on 2016-05-31 14:49
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('credit', '0006_auto_20160518_1252'),
    ]

    operations = [
        migrations.AlterField(
            model_name='credit',
            name='received_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
