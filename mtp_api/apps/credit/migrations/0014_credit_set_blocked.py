from django.db import migrations


def set_appropriate_blocked_credits(apps, schema_editor):
    Credit = apps.get_model('credit', 'Credit')
    Credit.objects.filter(
        transaction__isnull=False, transaction__incomplete_sender_info=True
    ).exclude(resolution='credited').update(blocked=True)


class Migration(migrations.Migration):

    dependencies = [
        ('credit', '0013_credit_blocked'),
        ('transaction', '0039_consistent_received_at_time'),
    ]

    operations = [
        migrations.RunPython(set_appropriate_blocked_credits)
    ]
