# Generated by Django 2.0.13 on 2019-12-10 16:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('credit', '0032_merge_20190218_1205'),
    ]

    operations = [
        migrations.AlterField(
            model_name='credit',
            name='resolution',
            field=models.CharField(choices=[('initial', 'Initial'), ('pending', 'Pending'), ('manual', 'Requires manual processing'), ('credited', 'Credited'), ('refunded', 'Refunded'), ('failed', 'Failed')], db_index=True, default='pending', max_length=50),
        ),
    ]
