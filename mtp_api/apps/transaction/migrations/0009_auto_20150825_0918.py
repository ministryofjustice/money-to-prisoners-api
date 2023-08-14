from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0008_auto_20150813_1314'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='transaction',
            options={'permissions': (('view_transaction', 'Can view transaction'), ('lock_transaction', 'Can lock transaction'), ('unlock_transaction', 'Can unlock transaction'), ('patch_credited_transaction', 'Can patch credited transaction')), 'ordering': ('received_at',)},
        ),
        migrations.AlterField(
            model_name='log',
            name='action',
            field=models.CharField(choices=[('created', 'Created'), ('locked', 'Locked'), ('unlocked', 'Unlocked'), ('credited', 'Credited')], max_length=50),
        ),
    ]
