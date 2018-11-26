from django.db import migrations, models


def fake_login_urls(apps, schema_editor):
    apps.get_model('mtp_auth', 'Role').objects \
        .filter(login_url__isnull=True) \
        .update(login_url='https://www.gov.uk/send-prisoner-money')


class Migration(migrations.Migration):
    dependencies = [
        ('mtp_auth', '0012_flags'),
    ]
    operations = [
        migrations.RunPython(code=fake_login_urls, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name='role',
            name='login_url',
            field=models.URLField(),
        ),
    ]
