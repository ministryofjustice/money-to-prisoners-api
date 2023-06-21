# Generated by Django 1.10.5 on 2017-05-05 15:56
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('credit', '0020_processingbatch'),
    ]

    operations = [
        migrations.AlterField(
            model_name='credit',
            name='resolution',
            field=models.CharField(choices=[('initial', 'Initial'), ('pending', 'Pending'), ('manual', 'Requires manual processing'), ('credited', 'Credited'), ('refunded', 'Refunded')], default='pending', max_length=50),
        ),
        migrations.AlterField(
            model_name='log',
            name='action',
            field=models.CharField(choices=[('created', 'Created'), ('locked', 'Locked'), ('unlocked', 'Unlocked'), ('credited', 'Credited'), ('uncredited', 'Uncredited'), ('refunded', 'Refunded'), ('reconciled', 'Reconciled'), ('reviewed', 'Reviewed'), ('manual', 'Marked for manual processing')], max_length=50),
        ),
    ]
