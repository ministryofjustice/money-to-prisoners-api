# Generated by Django 1.9.4 on 2016-09-05 15:20
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('credit', '0008_auto_20160616_1220'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='credit',
            options={'get_latest_by': 'received_at', 'ordering': ('received_at',), 'permissions': (('view_credit', 'Can view credit'), ('view_any_credit', 'Can view any credit'), ('lock_credit', 'Can lock credit'), ('unlock_credit', 'Can unlock credit'), ('patch_credited_credit', 'Can patch credited credit'))},
        ),
    ]
