# Generated by Django 2.0.13 on 2020-08-04 10:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('prison', '0018_prison_private_estate'),
    ]

    operations = [
        migrations.AlterField(
            model_name='prisonerlocation',
            name='active',
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
