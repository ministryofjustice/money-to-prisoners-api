# Generated by Django 2.2.19 on 2021-03-31 11:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mtp_auth', '0016_prison_optional_for_account_requests'),
    ]

    operations = [
        migrations.AddField(
            model_name='accountrequest',
            name='manager_email',
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
    ]
