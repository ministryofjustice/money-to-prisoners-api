import logging

from django.db import connection, models, transaction
from django.db.models import Count, Sum, Subquery, OuterRef, Q
from django.db.models.functions import Coalesce

from credit.models import Credit

logger = logging.getLogger('mtp')


class PrisonerProfileManager(models.Manager):
    def get_queryset(self):
        return PrisonerProfileQuerySet(model=self.model, using=self._db, hints=self._hints)

    @transaction.atomic
    def update_current_prisons(self):
        with connection.cursor() as cursor:
            cursor.execute(
                'UPDATE security_prisonerprofile '
                'SET current_prison_id = pl.prison_id '
                'FROM security_prisonerprofile AS pp '
                'LEFT OUTER JOIN prison_prisonerlocation AS pl '
                'ON pp.prisoner_number = pl.prisoner_number '
                'AND pl.active is True '
                'WHERE security_prisonerprofile.id = pp.id '
            )

    def get_for_credit(self, credit):
        if credit.prisoner_profile:
            return credit.prisoner_profile
        return self.get(prisoner_number=credit.prisoner_number)

    def get_for_disbursement(self, disbursement):
        if disbursement.prisoner_profile:
            return disbursement.prisoner_profile
        return self.get(prisoner_number=disbursement.prisoner_number)

    def create_or_update_for_credit(self, credit):
        assert credit.prison, 'Credit does not have a known prisoner'

        prisoner_profile, _ = self.update_or_create(
            prisoner_number=credit.prisoner_number,
            defaults=dict(
                prisoner_name=credit.prisoner_name,
                prisoner_dob=credit.prisoner_dob,
            )
        )
        if hasattr(credit, 'payment') and credit.payment.recipient_name:
            provided_name = credit.payment.recipient_name
            if not prisoner_profile.provided_names.filter(name=provided_name).exists():
                prisoner_profile.provided_names.create(name=provided_name)

        if credit.prison not in prisoner_profile.prisons.all():
            prisoner_profile.add_prison(credit.prison)
        credit.prisoner_profile = prisoner_profile
        credit.save()
        logger.info('Attached prisoner profile %s to credit %s', prisoner_profile, credit)
        return prisoner_profile

    def create_or_update_for_disbursement(self, disbursement):
        from prison.models import PrisonerLocation

        assert not disbursement.prisoner_profile, 'Prisoner profile already linked'

        prisoner_profile_defaults = {'prisoner_name': disbursement.prisoner_name}
        try:
            prisoner_location = PrisonerLocation.objects.get(
                prisoner_number=disbursement.prisoner_number, active=True
            )
            prisoner_profile_defaults.update(
                prisoner_dob=prisoner_location.prisoner_dob,
            )
        except PrisonerLocation.DoesNotExist:
            pass

        prisoner_profile, _ = self.update_or_create(
            prisoner_number=disbursement.prisoner_number,
            defaults=prisoner_profile_defaults,
        )
        prisoner_profile.add_prison(disbursement.prison)
        disbursement.prisoner_profile = prisoner_profile
        disbursement.save()
        return prisoner_profile


class SenderProfileManager(models.Manager):
    def get_queryset(self):
        return SenderProfileQuerySet(model=self.model, using=self._db, hints=self._hints)

    def get_anonymous_sender(self):
        """
        Represents senders where neither bank transfer nor debit card details are known
        """
        return self.get(
            bank_transfer_details__isnull=True,
            debit_card_details__isnull=True,
        )

    def get_or_create_anonymous_sender(self):
        try:
            return self.get_anonymous_sender()
        except self.model.DoesNotExist:
            return self.create()

    def get_for_credit(self, credit):
        if credit.sender_profile:
            return credit.sender_profile
        if hasattr(credit, 'transaction'):
            return self._get_for_bank_transfer(credit)
        elif hasattr(credit, 'payment'):
            return self._get_for_debit_card(credit)
        return self.get_or_create_anonymous_sender()

    def _get_for_bank_transfer(self, credit):
        return self.get(
            bank_transfer_details__sender_name=credit.sender_name,
            bank_transfer_details__sender_bank_account__sort_code=credit.sender_sort_code,
            bank_transfer_details__sender_bank_account__account_number=credit.sender_account_number,
            bank_transfer_details__sender_bank_account__roll_number=credit.sender_roll_number or '',
        )

    def _get_for_debit_card(self, credit):
        billing_address = credit.payment.billing_address
        normalised_postcode = billing_address.normalised_postcode if billing_address else None
        return self.get(
            debit_card_details__card_number_last_digits=credit.card_number_last_digits,
            debit_card_details__card_expiry_date=credit.card_expiry_date,
            debit_card_details__postcode=normalised_postcode,
        )

    def create_or_update_for_credit(self, credit):
        from credit.constants import CREDIT_RESOLUTION
        if hasattr(credit, 'transaction'):
            sender_profile = self._create_or_update_for_bank_transfer(credit)
        elif hasattr(credit, 'payment'):
            sender_profile = self._create_or_update_for_debit_card(credit)
        else:
            logger.error('Credit does not have a payment nor transaction', {'credit_id': credit.pk})
            sender_profile = self.get_or_create_anonymous_sender()

        # Annoyingly we still have to add this resolution clause for test setup, due to the fact that our test setup
        # does not go through the realistic state mutation properly, simply creating entities in their final state
        if (
            credit.prison
            and credit.resolution != CREDIT_RESOLUTION.FAILED
            and credit.prison not in sender_profile.prisons.all()
        ):
            sender_profile.add_prison(credit.prison)
        credit.sender_profile = sender_profile
        credit.save()
        logger.info('Attached sender profile %s to credit %s', sender_profile, credit)
        return sender_profile

    def _create_or_update_for_bank_transfer(self, credit):
        from security.models import BankAccount

        try:
            sender_profile = self._get_for_bank_transfer(credit)
        except self.model.DoesNotExist:
            bank_account, _ = BankAccount.objects.get_or_create(
                sort_code=credit.sender_sort_code,
                account_number=credit.sender_account_number,
                roll_number=credit.sender_roll_number or '',
            )
            sender_profile = self.create()
            sender_profile.bank_transfer_details.create(
                sender_name=credit.sender_name,
                sender_bank_account=bank_account,
            )

        return sender_profile

    def _create_or_update_for_debit_card(self, credit):
        billing_address = credit.payment.billing_address
        normalised_postcode = billing_address.normalised_postcode if billing_address else None
        try:
            sender_profile = self._get_for_debit_card(credit)
            debit_card_details = sender_profile.debit_card_details.first()
        except self.model.DoesNotExist:
            sender_profile = self.create()
            debit_card_details = sender_profile.debit_card_details.create(
                card_number_last_digits=credit.card_number_last_digits,
                card_expiry_date=credit.card_expiry_date,
                postcode=normalised_postcode,
            )

        sender_name = credit.payment.cardholder_name  # NB: was credit.sender_name
        if sender_name and not debit_card_details.cardholder_names.filter(name=sender_name).exists():
            debit_card_details.cardholder_names.create(name=sender_name)

        sender_email = credit.payment.email
        if sender_email and not debit_card_details.sender_emails.filter(email=sender_email).exists():
            debit_card_details.sender_emails.create(email=sender_email)

        billing_address.debit_card_sender_details = debit_card_details
        billing_address.save()

        return sender_profile


class RecipientProfileManager(models.Manager):
    def get_queryset(self):
        return RecipientProfileQuerySet(model=self.model, using=self._db, hints=self._hints)

    def get_cheque_recipient(self):
        """
        Represents all recipients who are sent disbursements by cheque
        """
        return self.get(
            bank_transfer_details__isnull=True
        )

    def get_or_create_cheque_recipient(self):
        try:
            return self.get_cheque_recipient()
        except self.model.DoesNotExist:
            return self.create()

    def get_for_disbursement(self, disbursement):
        if disbursement.recipient_profile:
            return disbursement.recipient_profile
        return self.get(
            bank_transfer_details__recipient_bank_account__sort_code=disbursement.sort_code,
            bank_transfer_details__recipient_bank_account__account_number=disbursement.account_number,
            bank_transfer_details__recipient_bank_account__roll_number=disbursement.roll_number or '',
        )

    def create_or_update_for_disbursement(self, disbursement):
        from disbursement.constants import DISBURSEMENT_METHOD
        from security.models import BankAccount

        assert not disbursement.recipient_profile, 'Recipient profile already linked'

        if disbursement.method == DISBURSEMENT_METHOD.CHEQUE:
            recipient_profile = self.get_or_create_cheque_recipient()
        else:
            try:
                recipient_profile = self.get_for_disbursement(disbursement)
            except self.model.DoesNotExist:
                bank_account, _ = BankAccount.objects.get_or_create(
                    sort_code=disbursement.sort_code,
                    account_number=disbursement.account_number,
                    roll_number=disbursement.roll_number or '',
                )
                recipient_profile = self.create()
                recipient_profile.bank_transfer_details.create(
                    recipient_bank_account=bank_account,
                )

        recipient_profile.prisons.add(disbursement.prison)
        disbursement.recipient_profile = recipient_profile
        disbursement.save()
        return recipient_profile


class PrisonerProfileQuerySet(models.QuerySet):
    def recalculate_totals(self):
        self.recalculate_credit_totals()
        self.recalculate_disbursement_totals()

    def recalculate_credit_totals(self):
        from credit.constants import CREDIT_RESOLUTION
        from credit.models import Credit
        from security.models import PrisonerProfile

        self.update(
            credit_count=Coalesce(Subquery(
                PrisonerProfile.objects.filter(
                    id=OuterRef('id'),
                ).annotate(
                    calculated=Count(
                        'credits',
                        distinct=True,
                        filter=Q(credits__resolution=CREDIT_RESOLUTION.CREDITED)
                    )
                ).values('calculated')[:1]
            ), 0),
            credit_total=Coalesce(Subquery(
                PrisonerProfile.objects.filter(
                    id=OuterRef('id'),
                ).annotate(
                    calculated=Sum(
                        'credits__amount',
                        filter=Q(credits__resolution=CREDIT_RESOLUTION.CREDITED)
                    )
                ).values('calculated')[:1]
            ), 0),
        )
        new_credits = Credit.objects.filter(
            prisoner_profile__in=self,
            resolution=CREDIT_RESOLUTION.CREDITED,
            is_counted_in_prisoner_profile_total=False
        )
        new_credits_ids = [c.id for c in new_credits]
        new_credits.update(is_counted_in_prisoner_profile_total=True)
        # This is kinda grim, but I don't like the idea of passing around stale
        # objects. If anyone can think of a nicer way to do these please feel free to refactor
        return Credit.objects.filter(id__in=new_credits_ids)

    def recalculate_disbursement_totals(self):
        from security.models import PrisonerProfile

        self.update(
            disbursement_count=Coalesce(Subquery(
                PrisonerProfile.objects.filter(
                    id=OuterRef('id'),
                ).annotate(
                    calculated=Count('disbursements', distinct=True)
                ).values('calculated')[:1]
            ), 0),
            disbursement_total=Coalesce(Subquery(
                PrisonerProfile.objects.filter(
                    id=OuterRef('id'),
                ).annotate(
                    calculated=Sum('disbursements__amount')
                ).values('calculated')[:1]
            ), 0),
        )


class SenderProfileQuerySet(models.QuerySet):
    def recalculate_totals(self):
        self.recalculate_credit_totals()

    def recalculate_credit_totals(self):
        from credit.constants import CREDIT_RESOLUTION
        from credit.models import Credit
        from security.models import SenderProfile

        self.update(
            credit_count=Coalesce(Subquery(
                SenderProfile.objects.filter(
                    id=OuterRef('id'),
                ).annotate(
                    calculated=Count(
                        'credits',
                        distinct=True,
                        filter=Q(credits__resolution=CREDIT_RESOLUTION.CREDITED)
                    )
                ).values('calculated')[:1]
            ), 0),
            credit_total=Coalesce(Subquery(
                SenderProfile.objects.filter(
                    id=OuterRef('id'),
                ).annotate(
                    calculated=Sum(
                        'credits__amount',
                        filter=Q(credits__resolution=CREDIT_RESOLUTION.CREDITED)
                    )
                ).values('calculated')[:1]
            ), 0),
        )
        new_credits = Credit.objects.filter(
            sender_profile__in=self,
            resolution=CREDIT_RESOLUTION.CREDITED,
            is_counted_in_sender_profile_total=False
        )
        new_credits_ids = [c.id for c in new_credits]
        new_credits.update(is_counted_in_sender_profile_total=True)
        # This is kinda grim, but I don't like the idea of passing around stale
        # objects. If anyone can think of a nicer way to do these please feel free to refactor
        return Credit.objects.filter(id__in=new_credits_ids)


class RecipientProfileQuerySet(models.QuerySet):
    def recalculate_totals(self):
        self.recalculate_disbursement_totals()

    def recalculate_disbursement_totals(self):
        from security.models import RecipientProfile

        self.update(
            disbursement_count=Coalesce(Subquery(
                RecipientProfile.objects.filter(
                    id=OuterRef('id'),
                ).annotate(
                    calculated=Count('disbursements', distinct=True)
                ).values('calculated')[:1]
            ), 0),
            disbursement_total=Coalesce(Subquery(
                RecipientProfile.objects.filter(
                    id=OuterRef('id'),
                ).annotate(
                    calculated=Sum('disbursements__amount')
                ).values('calculated')[:1]
            ), 0),
        )


class CheckManager(models.Manager):
    ENABLED_RULE_CODES = ('FIUMONP', 'FIUMONS', 'CSFREQ', 'CSNUM', 'CPNUM')

    def create_for_credit(self, credit):
        from notification.rules import RULES
        from security.constants import CHECK_STATUS
        from security.models import CheckAutoAcceptRule

        matched_rule_codes = self._get_matching_rules(credit)
        auto_accept_rule_state = None
        if matched_rule_codes:
            description = [RULES[rule_code].description for rule_code in matched_rule_codes]
            auto_accept_rule = CheckAutoAcceptRule.objects.get_active_auto_accept_for_credit(credit)
            if auto_accept_rule:
                # If active auto_accept rule:
                # * `auto_accept_rule` will be `CheckAutoAcceptRule()`
                # * No FIU check required
                status = CHECK_STATUS.ACCEPTED
                auto_accept_rule_state = auto_accept_rule.get_latest_state()
            else:
                # If no active auto_accept rule:
                # * `auto_accept_rule` will be None
                # * FIU check required
                status = CHECK_STATUS.PENDING
        else:
            description = ['Credit matched no rules and was automatically accepted']
            status = CHECK_STATUS.ACCEPTED

        return self.create(
            credit=credit,
            status=status,
            description=description,
            auto_accept_rule_state=auto_accept_rule_state,
            rules=matched_rule_codes,
        )

    def _get_matching_rules(self, credit):
        from notification.rules import RULES

        matched_rule_codes = []
        for rule_code in self.ENABLED_RULE_CODES:
            rule = RULES[rule_code]
            if rule.applies_to(credit) and rule.triggered(credit):
                matched_rule_codes.append(rule_code)
        return matched_rule_codes


class CheckAutoAcceptRuleManager(models.Manager):

    def get_active_auto_accept_for_credit(self, credit: Credit):
        auto_accept_rule = self.filter(
            debit_card_sender_details=credit.sender_profile.debit_card_details.first(),
            prisoner_profile=credit.prisoner_profile
        ).first()
        if auto_accept_rule and auto_accept_rule.is_active():
            return auto_accept_rule
        else:
            return None
