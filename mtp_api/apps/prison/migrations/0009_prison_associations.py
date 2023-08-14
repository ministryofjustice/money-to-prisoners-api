# Generated by Django 1.9.4 on 2016-08-08 12:04
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('prison', '0008_auto_20160630_1515'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='category',
            options={'ordering': ('name',), 'verbose_name_plural': 'categories'},
        ),
        migrations.AlterModelOptions(
            name='population',
            options={'ordering': ('name',)},
        ),
        migrations.AlterField(
            model_name='category',
            name='name',
            field=models.CharField(max_length=30),
        ),
        migrations.AlterField(
            model_name='population',
            name='name',
            field=models.CharField(max_length=30),
        ),
    ]
