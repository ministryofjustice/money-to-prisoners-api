# Generated by Django 1.9.4 on 2016-11-08 12:43
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('prison', '0010_prison_pre_approval_required'),
    ]

    operations = [
        migrations.AddField(
            model_name='prisonerlocation',
            name='active',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterModelOptions(
            name='prison',
            options={'ordering': ('name',)},
        ),
    ]
