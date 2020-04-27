import logging

from django.db.transaction import atomic
from django.core.management import BaseCommand, CommandError

from credit.models import Credit
from disbursement.constants import DISBURSEMENT_RESOLUTION
from disbursement.models import Disbursement
from notification.tasks import create_notification_events
from security.models import PrisonerProfile, SenderProfile, RecipientProfile

logger = logging.getLogger('mtp')


class Command(BaseCommand):
    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--batch-size', type=int, default=200,
                            help='Number of objects to process in one atomic transaction')
        parser.add_argument('--recalculate-totals', action='store_true', help='Recalculates the counts and totals only')
        parser.add_argument('--recreate', action='store_true', help='Deletes existing profiles')

    def handle(self, **options):
        if options['recalculate_totals'] and options['recreate']:
            raise CommandError('Cannot recalculate totals when deleting all profiles')

        batch_size = options['batch_size']
        if batch_size < 1:
            raise CommandError('Batch size must be at least 1')

        if options['recalculate_totals']:
            self.handle_totals(batch_size=batch_size)
        else:
            self.handle_update(batch_size=batch_size, recreate=options['recreate'])

    def handle_update(self, batch_size, recreate):
        if recreate:
            self.delete_profiles()

        try:
            self.handle_credit_update(batch_size)
            self.handle_disbursement_update(batch_size)
        finally:
            self.stdout.write('Updating prisoner profiles for current locations')
            PrisonerProfile.objects.update_current_prisons()

    def handle_credit_update(self, batch_size):
        # Implicit filter on resolution not in initial / failed through CompletedCreditManager.get_queryset()
        new_credits = Credit.objects.filter(is_counted_in_sender_profile_total=False).order_by('pk')
        new_credits_count = new_credits.count()
        if not new_credits_count:
            self.stdout.write(self.style.SUCCESS('No new credits'))
            return
        else:
            self.stdout.write(f'Updating profiles for (at least) {new_credits_count} new credits')

        processed_count = 0
        while True:
            count = self.process_credit_batch(new_credits[0:batch_size])
            if count == 0:
                break
            processed_count += count
            self.stdout.write(f'Processed {processed_count} credits')

        self.stdout.write(self.style.SUCCESS('Processed all credits'))

    def handle_disbursement_update(self, batch_size):
        new_disbursements = Disbursement.objects.filter(
            recipient_profile__isnull=True,
            resolution=DISBURSEMENT_RESOLUTION.SENT,
        ).order_by('pk')
        new_disbursements_count = new_disbursements.count()
        if not new_disbursements_count:
            self.stdout.write(self.style.SUCCESS('No new disbursements'))
            return
        else:
            self.stdout.write(f'Updating profiles for (at least) {new_disbursements_count} new disbursements')

        processed_count = 0
        while True:
            count = self.process_disbursement_batch(new_disbursements[0:batch_size])
            if count == 0:
                break
            processed_count += count
            self.stdout.write(f'Processed {processed_count} disbursements')

        self.stdout.write(self.style.SUCCESS('Processed all disbursements'))

    @atomic()
    def process_credit_batch(self, new_credits):
        sender_profiles = []
        prisoner_profiles = []
        credits_with_sender_profiles = []
        for credit in new_credits:
            self.create_or_update_profiles_for_credit(credit)
            if credit.sender_profile:
                sender_profiles.append(credit.sender_profile.pk)
                credits_with_sender_profiles.append(credit)
            else:
                logger.warning('Sender profile could not be found for credit %s', credit)
            if credit.prisoner_profile:
                prisoner_profiles.append(credit.prisoner_profile.pk)
            else:
                logger.warning('Prisoner profile could not be found for credit %s', credit)

        SenderProfile.objects.filter(
            pk__in=sender_profiles
        ).recalculate_credit_totals()
        PrisonerProfile.objects.filter(
            pk__in=prisoner_profiles
        ).recalculate_credit_totals()

        for credit in credits_with_sender_profiles:
            credit.is_counted_in_sender_profile_total = True
            credit.save()
        create_notification_events(records=new_credits)
        return len(new_credits)

    @atomic()
    def process_disbursement_batch(self, new_disbursements):
        recipient_profiles = []
        prisoner_profiles = []
        for disbursement in new_disbursements:
            self.create_or_update_profiles_for_disbursement(disbursement)
            if disbursement.recipient_profile:
                recipient_profiles.append(disbursement.recipient_profile.pk)
            if disbursement.prisoner_profile:
                prisoner_profiles.append(disbursement.prisoner_profile.pk)

        RecipientProfile.objects.filter(
            pk__in=recipient_profiles
        ).recalculate_disbursement_totals()
        PrisonerProfile.objects.filter(
            pk__in=prisoner_profiles
        ).recalculate_disbursement_totals()

        create_notification_events(records=new_disbursements)
        return len(new_disbursements)

    def create_or_update_profiles_for_credit(self, credit):
        if not credit.sender_profile:
            # TODO this method does not need to return, pull sender_proffile off credit object
            sender_profile = SenderProfile.objects.create_or_update_for_credit(credit)
        if credit.prison and credit.sender_profile and not credit.prisoner_profile:
            prisoner_profile = PrisonerProfile.objects.create_or_update_for_credit(credit)
            prisoner_profile.senders.add(sender_profile)

    def create_or_update_profiles_for_disbursement(self, disbursement):
        recipient_profile = RecipientProfile.objects.create_or_update_for_disbursement(disbursement)
        prisoner_profile = PrisonerProfile.objects.create_or_update_for_disbursement(disbursement)
        prisoner_profile.recipients.add(recipient_profile)

    def handle_totals(self, batch_size):
        profiles = (
            (SenderProfile, 'sender'),
            (PrisonerProfile, 'prisoner'),
            (RecipientProfile, 'recipient'),
        )
        for model, name in profiles:
            queryset = model.objects.order_by('pk').all()
            count = queryset.count()
            if not count:
                self.stdout.write(self.style.SUCCESS(f'No {name} profiles to update'))
                return
            else:
                self.stdout.write(f'Updating {count} {name} profile totals')

            processed_count = 0
            for offset in range(0, count, batch_size):
                batch = slice(offset, min(offset + batch_size, count))
                queryset[batch].recalculate_totals()
                processed_count += batch_size
                self.stdout.write(f'Processed up to {processed_count} {name} profiles')

        self.stdout.write(self.style.SUCCESS('Done'))

    @atomic()
    def delete_profiles(self):
        from django.apps import apps
        from django.core.management.color import no_style
        from django.db import connection

        PrisonerProfile.objects.all().delete()
        SenderProfile.objects.all().delete()
        RecipientProfile.objects.all().delete()

        security_app = apps.app_configs['security']
        with connection.cursor() as cursor:
            for reset_sql in connection.ops.sequence_reset_sql(no_style(), security_app.get_models()):
                cursor.execute(reset_sql)
