# Generated by Django 2.0.13 on 2020-03-10 16:37

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('security', '0026_check_rejection_reason'),
    ]

    operations = [
        migrations.RenameField(
            model_name='check',
            old_name='rejection_reason',
            new_name='decision_reason',
        ),
    ]
