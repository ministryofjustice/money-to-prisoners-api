# Generated by Django 1.9.4 on 2016-03-29 14:14
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0007_balance'),
    ]

    operations = [
        migrations.AlterField(
            model_name='batch',
            name='user',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
    ]
