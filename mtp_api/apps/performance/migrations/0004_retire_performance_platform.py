from django.db import migrations


def remove_performance_platform_update(apps, schema_editor):
    cls = apps.get_model('core', 'ScheduledCommand')
    cls.objects.filter(name='update_performance_platform').delete()


def restore_performance_platform_update(apps, schema_editor):
    cls = apps.get_model('core', 'ScheduledCommand')
    cls.objects.create(
        name='update_performance_platform',
        arg_string='--resources completion-rate',
        cron_entry='0 5 * * Mon',
    )
    cls.objects.create(
        name='update_performance_platform',
        arg_string='--resources transactions-by-channel-type',
        cron_entry='50 22 * * *',
    )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0005_delete_token'),
        ('performance', '0003_credit_amounts'),
    ]
    operations = [
        migrations.RunPython(
            remove_performance_platform_update,
            reverse_code=restore_performance_platform_update,
        )
    ]
