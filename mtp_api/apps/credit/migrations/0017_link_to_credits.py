import warnings

from django.conf import settings
from django.db import migrations


def link_credits(apps, _):
    if settings.ENVIRONMENT == 'prod':
        warnings.warn('Remember to run a manual update to link credits to security profiles')
        return

    from security.models import SenderProfile, PrisonerProfile

    credit_cls = apps.get_model('credit', 'Credit')

    sender_cls = apps.get_model('security', 'SenderProfile')
    sender_cls.credit_filters = SenderProfile.credit_filters
    senders = sender_cls.objects.all().order_by('pk')
    count = senders.count()
    print('Linking %d sender profiles to their credits' % count)
    for index, sender in enumerate(senders):
        if index % 100 == 0:
            print('%0.0f%%' % (index / count * 100), sender.pk)
        matching_credits = credit_cls.objects.filter(sender.credit_filters).only('pk')
        for credit in matching_credits:
            credit.sender_profile_id = sender.pk
            credit.save()

    prisoner_cls = apps.get_model('security', 'PrisonerProfile')
    prisoner_cls.credit_filters = PrisonerProfile.credit_filters
    prisoners = prisoner_cls.objects.all().order_by('pk')
    count = prisoners.count()
    print('Linking %d prisoner profiles to their credits' % count)
    for index, prisoner in enumerate(prisoners):
        if index % 100 == 0:
            print('%0.0f%%' % (index / count * 100), prisoner.pk)
        matching_credits = credit_cls.objects.filter(prisoner.credit_filters).only('pk')
        for credit in matching_credits:
            credit.prisoner_profile_id = prisoner.pk
            credit.save()


class Migration(migrations.Migration):
    dependencies = [
        ('credit', '0016_link_to_credits'),
    ]
    operations = [
        migrations.RunPython(code=link_credits, reverse_code=migrations.RunPython.noop),
    ]
