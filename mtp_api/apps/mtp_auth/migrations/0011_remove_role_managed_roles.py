from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('mtp_auth', '0010_accountrequest'),
    ]
    operations = [
        migrations.RemoveField(model_name='role', name='managed_roles'),
    ]
