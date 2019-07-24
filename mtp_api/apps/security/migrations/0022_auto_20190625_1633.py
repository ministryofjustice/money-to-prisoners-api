# Generated by Django 2.0.13 on 2019-06-25 15:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('security', '0021_auto_20190625_1632'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='prisonerprofile',
            index=models.Index(fields=['credit_count'], name='security_pr_credit__cad7c2_idx'),
        ),
        migrations.AddIndex(
            model_name='prisonerprofile',
            index=models.Index(fields=['credit_total'], name='security_pr_credit__71ade5_idx'),
        ),
        migrations.AddIndex(
            model_name='prisonerprofile',
            index=models.Index(fields=['disbursement_count'], name='security_pr_disburs_26653f_idx'),
        ),
        migrations.AddIndex(
            model_name='prisonerprofile',
            index=models.Index(fields=['disbursement_total'], name='security_pr_disburs_74948c_idx'),
        ),
        migrations.AddIndex(
            model_name='recipientprofile',
            index=models.Index(fields=['disbursement_count'], name='security_re_disburs_1ea4fb_idx'),
        ),
        migrations.AddIndex(
            model_name='recipientprofile',
            index=models.Index(fields=['disbursement_total'], name='security_re_disburs_478726_idx'),
        ),
        migrations.AddIndex(
            model_name='senderprofile',
            index=models.Index(fields=['credit_count'], name='security_se_credit__fcd1fc_idx'),
        ),
        migrations.AddIndex(
            model_name='senderprofile',
            index=models.Index(fields=['credit_total'], name='security_se_credit__cd9fdb_idx'),
        ),
    ]
