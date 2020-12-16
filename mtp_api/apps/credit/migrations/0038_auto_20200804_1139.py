# Generated by Django 2.0.13 on 2020-08-04 10:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('credit', '0037_populate-is_counted_in_glob_profile_total'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='credit',
            index=models.Index(fields=['owner_id', 'reconciled', 'resolution'], name='credit_cred_owner_i_cac17f_idx'),
        ),
    ]