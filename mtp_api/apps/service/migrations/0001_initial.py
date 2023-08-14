# Generated by Django 1.9.4 on 2016-09-21 16:48
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Downtime',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('service', models.CharField(choices=[('gov_uk_pay', 'GOV.UK Pay')], max_length=50)),
                ('start', models.DateTimeField()),
                ('end', models.DateTimeField(blank=True, null=True)),
            ],
        ),
    ]
