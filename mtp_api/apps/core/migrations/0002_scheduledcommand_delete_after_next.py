# Generated by Django 1.9.12 on 2017-01-13 11:46
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduledcommand',
            name='delete_after_next',
            field=models.BooleanField(default=False),
        ),
    ]
