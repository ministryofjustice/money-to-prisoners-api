import re

from django.db import migrations


def migrate_saved_searches(apps, schema_editor):
    SenderProfile = apps.get_model('security', 'SenderProfile')
    PrisonerProfile = apps.get_model('security', 'PrisonerProfile')
    SavedSearch = apps.get_model('security', 'SavedSearch')

    sender = re.compile('/senders/([0-9]+)/')
    prisoner = re.compile('/prisoners/([0-9]+)/')

    migrated = 0
    for search in SavedSearch.objects.all():
        sender_match = sender.search(search.site_url)
        if sender_match:
            sender_id = sender_match.groups(1)[0]
            try:
                sender_profile = SenderProfile.objects.get(pk=sender_id)
                bank_details = sender_profile.bank_transfer_details.first()
                card_details = sender_profile.debit_card_details.first()
                if bank_details:
                    bank_details.sender_bank_account.monitoring_users.add(search.user)
                elif card_details:
                    card_details.monitoring_users.add(search.user)
                else:
                    print(
                        'No sender details for profile %s for search %s'
                        % (sender_id, search.pk,)
                    )
            except SenderProfile.DoesNotExist:
                print(
                    'SenderProfile %s not found for search %s'
                    % (sender_id, search.pk,)
                )
        else:
            prisoner_match = prisoner.search(search.site_url)
            if prisoner_match:
                prisoner_id = prisoner_match.groups(1)[0]
                try:
                    prisoner_profile = PrisonerProfile.objects.get(pk=prisoner_id)
                    prisoner_profile.monitoring_users.add(search.user)
                except SenderProfile.DoesNotExist:
                    print(
                        'PrisonerProfile %s not found for search %s'
                        % (prisoner_id, search.pk,)
                    )
            else:
                print('Search %s not matched' % search.pk)
                continue
        migrated += 1

    print('Migrated %s searches' % migrated)


class Migration(migrations.Migration):
    dependencies = [
        ('security', '0023_auto_20190625_1634'),
    ]
    operations = [
        migrations.RunPython(migrate_saved_searches, reverse_code=migrations.RunPython.noop)
    ]
