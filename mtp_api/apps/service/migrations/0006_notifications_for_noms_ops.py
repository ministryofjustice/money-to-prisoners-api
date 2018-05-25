from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('service', '0005_notification_levels'),
    ]
    operations = [
        migrations.AlterField(
            model_name='notification',
            name='target',
            field=models.CharField(choices=[('cashbook_login', 'Cashbook: before login'), ('cashbook_all', 'Cashbook: all apps'), ('cashbook_cashbook', 'Cashbook: cashbook app'), ('cashbook_disbursements', 'Cashbook: disbursements app'), ('noms_ops_login', 'Noms Ops: before login'), ('noms_ops_security_dashboard', 'Noms Ops: security dashboard')], max_length=30),
        ),
    ]
