# Generated by Django 1.9.4 on 2016-06-16 11:20
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0006_auto_20160531_1553'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='payment',
            options={'get_latest_by': 'created', 'ordering': ('created',), 'permissions': (('view_payment', 'Can view payment'),)},
        ),
        migrations.AlterField(
            model_name='payment',
            name='email',
            field=models.EmailField(blank=True, help_text='Specified by sender for confirmation emails', max_length=254, null=True),
        ),
        migrations.AlterField(
            model_name='payment',
            name='recipient_name',
            field=models.CharField(blank=True, help_text='As specified by the sender', max_length=250, null=True),
        ),
    ]
