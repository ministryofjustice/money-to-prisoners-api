# Generated by Django 1.10.7 on 2017-11-10 12:21
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('disbursement', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='disbursement',
            name='prison',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='prison.Prison'),
        ),
        migrations.AlterField(
            model_name='disbursement',
            name='prisoner_number',
            field=models.CharField(max_length=250),
        ),
    ]
