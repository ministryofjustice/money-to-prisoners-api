from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('service', '0006_notifications_for_noms_ops'),
    ]
    operations = [
        migrations.AlterField(
            model_name='notification',
            name='target',
            field=models.CharField(
                choices=[
                    ('bankadmin_login', 'Bank admin: before login'),
                    ('bankadmin_dashboard', 'Bank admin: dashboard'),
                    ('cashbook_login', 'Cashbook: before login'),
                    ('cashbook_dashboard', 'Cashbook: dashboard'),
                    ('cashbook_all', 'Cashbook: all apps'),
                    ('cashbook_cashbook', 'Cashbook: cashbook app'),
                    ('cashbook_disbursements', 'Cashbook: disbursements app'),
                    ('noms_ops_login', 'Noms Ops: before login'),
                    ('noms_ops_security_dashboard', 'Noms Ops: security dashboard'),
                    ('send_money_landing', 'Send Money: landing page'),
                ],
                max_length=30,
            ),
        ),
    ]
