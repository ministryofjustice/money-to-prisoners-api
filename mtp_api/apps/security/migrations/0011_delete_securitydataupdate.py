# Generated by Django 1.10.5 on 2017-03-01 15:31
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('security', '0010_prisoner_profile_uniqueness'),
    ]
    operations = [
        migrations.DeleteModel(name='SecurityDataUpdate'),
    ]