import logging

from django.db.models import Subquery
from django.db.transaction import atomic
from django.core.management import BaseCommand, CommandError

from credit.constants import CREDIT_RESOLUTION
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
        # TODO Remove below function once the logs show that it consistently
        # does not operate on any credits
        self.handle_profile_attachment_for_legacy_credits(batch_size)
        self.handle_credit_update_for_attached_prisoner_profiles(batch_size)
        self.handle_credit_update_for_attached_sender_profiles(batch_size)

    def handle_profile_attachment_for_legacy_credits(self, batch_size):
        # Implicit filter on resolution not in initial / failed through CompletedCreditManager.get_queryset()
        new_credits = Credit.objects.filter(
            sender_profile__isnull=True
        ).order_by('pk')
        new_credits_count = new_credits.count()
        if not new_credits_count:
            self.stdout.write(self.style.SUCCESS('Legacy Credits: No new credits'))
            return
        else:
            self.stdout.write(f'Legacy Credits: Updating profiles for (at least) {new_credits_count} new credits')

        processed_count = 0
        while True:
            count = self.attach_profiles_for_legacy_credits(new_credits[0:batch_size])
            if count == 0:
                break
            processed_count += count
            self.stdout.write(f'Legacy Credits: Processed {processed_count} credits')

        self.stdout.write(self.style.SUCCESS('Legacy Credits: Processed all credits'))

    def handle_credit_update_for_attached_prisoner_profiles(self, batch_size):
        # Now that we have the association between prisoner_profile/prisoner_profile populated, it makes sense to run
        # this job once per prisoner/prisoner profile instead of once per credit

        # The reason why we're using is_counted_in_sender_profile_total is because sender_profile will always be able
        # to be associated, therefore if the sender profile is not associated we know it also needs a prisoner profile
        prisoner_profiles = PrisonerProfile.objects.filter(
            credits__is_counted_in_prisoner_profile_total=False,
            credits__resolution=CREDIT_RESOLUTION.CREDITED
        ).order_by('pk')
        prisoner_profiles_count = prisoner_profiles.count()
        if not prisoner_profiles_count:
            self.stdout.write(self.style.SUCCESS('No prisoner profiles require updating'))
            return
        else:
            self.stdout.write(f'Updating {prisoner_profiles_count} prisoner profiles')

        processed_new_credits_count = 0
        while True:
            count = self.calculate_credit_totals_for_prisoner_profiles(prisoner_profiles[0:batch_size])
            if count == 0:
                break
            processed_new_credits_count += count
            self.stdout.write(
                f'Processed {prisoner_profiles_count} prisoner profiles for {processed_new_credits_count} new credits'
            )

        self.stdout.write(self.style.SUCCESS('Updated all prisoner profiles'))

    def handle_credit_update_for_attached_sender_profiles(self, batch_size):
        # Now that we have the association between sender_profile/sender_profile populated, it makes sense to run
        # this job once per sender/sender profile instead of once per credit
        sender_profiles = SenderProfile.objects.filter(
            credits__is_counted_in_sender_profile_total=False,
            credits__resolution=CREDIT_RESOLUTION.CREDITED
        ).order_by('pk')
        sender_profiles_count = sender_profiles.count()
        if not sender_profiles_count:
            self.stdout.write(self.style.SUCCESS('No sender profiles require updating'))
            return
        else:
            self.stdout.write(f'Updating {sender_profiles_count} sender profiles')

        processed_new_credits_count = 0
        while True:
            count = self.calculate_credit_totals_for_sender_profiles(sender_profiles[0:batch_size])
            if count == 0:
                break
            processed_new_credits_count += count
            self.stdout.write(
                f'Processed {sender_profiles_count} sender profiles for {processed_new_credits_count} new credits'
            )

        self.stdout.write(self.style.SUCCESS('Updated all sender profiles'))

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
    def attach_profiles_for_legacy_credits(self, new_credits):
        sender_profiles = []
        prisoner_profiles = []
        for credit in new_credits:
            self.create_or_update_profiles_for_credit(credit)
            if credit.sender_profile:
                sender_profiles.append(credit.sender_profile.pk)
            else:
                logger.warning('Sender profile could not be found for credit %s', credit)
            if credit.prisoner_profile:
                prisoner_profiles.append(credit.prisoner_profile.pk)
            else:
                logger.warning('Prisoner profile could not be found for credit %s', credit)

        # TODO this was previous behaviour, but I feel like it might not be appropriate now
        return len(new_credits)

    @atomic()
    def calculate_credit_totals_for_prisoner_profiles(self, prisoner_profiles):
        new_credits = PrisonerProfile.objects.filter(
            pk__in=prisoner_profiles
        ).recalculate_credit_totals()
        return len(new_credits)

    @atomic()
    def calculate_credit_totals_for_sender_profiles(self, sender_profiles):
        new_credits = SenderProfile.objects.filter(
            pk__in=sender_profiles
        ).recalculate_credit_totals()

        # The reason why we dispatched notifications on calculation of sender total and not prisoner is because we
        # don't want to duplicate notifications and because we know that a credit will always
        # have a sender, but potentially may not have a prisoner associated.
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
