from django.db import connection, models, transaction
from django.db.models import Count, Sum, Subquery, OuterRef, Q
from django.db.models.functions import Coalesce

from security.constants import TIME_PERIOD, get_start_date_for_time_period


class PrisonerProfileManager(models.Manager):

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


class SenderProfileManager(models.Manager):

    def get_anonymous_sender(self):
        return self.get(
            bank_transfer_details__isnull=True,
            debit_card_details__isnull=True
        )


class RecipientProfileManager(models.Manager):

    def get_cheque_recipient(self):
        return self.get(
            bank_transfer_details__isnull=True
        )


class TotalsQuerySet(models.QuerySet):

    @property
    def profile_class(self):
        return NotImplemented

    @property
    def profile_field(self):
        return self.profile_class.totals.rel.remote_field.name

    def create_totals_for_profile(self, profile):
        new_totals = []
        for time_period in TIME_PERIOD.values:
            new_totals.append(self.model(
                **{self.profile_field: profile, 'time_period': time_period}
            ))
        self.bulk_create(new_totals)


class CreditTotalsMixin:

    def update_credit_counts(self):
        for time_period in TIME_PERIOD.values:
            start = get_start_date_for_time_period(time_period)
            self.filter(time_period=time_period).update(
                credit_count=Coalesce(Subquery(
                    self.profile_class.objects.filter(
                        id=OuterRef('%s_id' % self.profile_field),
                    ).annotate(
                        credit_count=Count(
                            'credits',
                            filter=Q(
                                credits__received_at__gte=start,
                            ),
                            distinct=True
                        )
                    ).values('credit_count')[:1]
                ), 0)
            )

    def update_credit_totals(self):
        for time_period in TIME_PERIOD.values:
            start = get_start_date_for_time_period(time_period)
            self.filter(time_period=time_period).update(
                credit_total=Coalesce(Subquery(
                    self.profile_class.objects.filter(
                        id=OuterRef('%s_id' % self.profile_field),
                    ).annotate(
                        credit_total=Sum(
                            'credits__amount',
                            filter=Q(
                                credits__received_at__gte=start,
                            )
                        )
                    ).values('credit_total')[:1]
                ), 0)
            )


class DisbursementTotalsMixin:

    def update_disbursement_counts(self):
        for time_period in TIME_PERIOD.values:
            start = get_start_date_for_time_period(time_period)
            self.filter(time_period=time_period).update(
                disbursement_count=Coalesce(Subquery(
                    self.profile_class.objects.filter(
                        id=OuterRef('%s_id' % self.profile_field),
                    ).annotate(
                        disbursement_count=Count(
                            'disbursements',
                            filter=Q(
                                disbursements__created__gte=start,
                            ),
                            distinct=True
                        )
                    ).values('disbursement_count')[:1]
                ), 0)
            )

    def update_disbursement_totals(self):
        for time_period in TIME_PERIOD.values:
            start = get_start_date_for_time_period(time_period)
            self.filter(time_period=time_period).update(
                disbursement_total=Coalesce(Subquery(
                    self.profile_class.objects.filter(
                        id=OuterRef('%s_id' % self.profile_field),
                    ).annotate(
                        disbursement_total=Sum(
                            'disbursements__amount',
                            filter=Q(
                                disbursements__created__gte=start,
                            )
                        )
                    ).values('disbursement_total')[:1]
                ), 0)
            )


class SenderTotalsQuerySet(TotalsQuerySet, CreditTotalsMixin):

    @property
    def profile_class(self):
        from security.models import SenderProfile
        return SenderProfile

    def update_prisoner_counts(self):
        for time_period in TIME_PERIOD.values:
            start = get_start_date_for_time_period(time_period)
            self.filter(time_period=time_period).update(
                prisoner_count=Coalesce(Subquery(
                    self.profile_class.objects.filter(
                        id=OuterRef('sender_profile_id'),
                    ).annotate(
                        prisoner_count=Count(
                            'credits__prisoner_profile',
                            filter=Q(
                                credits__received_at__gte=start,
                            ),
                            distinct=True
                        )
                    ).values('prisoner_count')[:1]
                ), 0)
            )

    def update_prison_counts(self):
        for time_period in TIME_PERIOD.values:
            start = get_start_date_for_time_period(time_period)
            self.filter(time_period=time_period).update(
                prison_count=Coalesce(Subquery(
                    self.profile_class.objects.filter(
                        id=OuterRef('sender_profile_id'),
                    ).annotate(
                        prison_count=Count(
                            'credits__prison',
                            filter=Q(
                                credits__received_at__gte=start,
                            ),
                            distinct=True
                        )
                    ).values('prison_count')[:1]
                ), 0)
            )

    def update_all_totals(self):
        self.update_credit_counts()
        self.update_credit_totals()
        self.update_prisoner_counts()
        self.update_prison_counts()


class RecipientTotalsQuerySet(TotalsQuerySet, DisbursementTotalsMixin):

    @property
    def profile_class(self):
        from security.models import RecipientProfile
        return RecipientProfile

    def update_prisoner_counts(self):
        for time_period in TIME_PERIOD.values:
            start = get_start_date_for_time_period(time_period)
            self.filter(time_period=time_period).update(
                prisoner_count=Coalesce(Subquery(
                    self.profile_class.objects.filter(
                        id=OuterRef('recipient_profile_id'),
                    ).annotate(
                        prisoner_count=Count(
                            'disbursements__prisoner_profile',
                            filter=Q(
                                disbursements__created__gte=start,
                            ),
                            distinct=True
                        )
                    ).values('prisoner_count')[:1]
                ), 0)
            )

    def update_prison_counts(self):
        for time_period in TIME_PERIOD.values:
            start = get_start_date_for_time_period(time_period)
            self.filter(time_period=time_period).update(
                prison_count=Coalesce(Subquery(
                    self.profile_class.objects.filter(
                        id=OuterRef('recipient_profile_id'),
                    ).annotate(
                        prison_count=Count(
                            'disbursements__prison',
                            filter=Q(
                                disbursements__created__gte=start,
                            ),
                            distinct=True
                        )
                    ).values('prison_count')[:1]
                ), 0)
            )

    def update_all_totals(self):
        self.update_disbursement_counts()
        self.update_disbursement_totals()
        self.update_prisoner_counts()
        self.update_prison_counts()


class PrisonerTotalsQuerySet(TotalsQuerySet, CreditTotalsMixin, DisbursementTotalsMixin):

    @property
    def profile_class(self):
        from security.models import PrisonerProfile
        return PrisonerProfile

    def update_sender_counts(self):
        for time_period in TIME_PERIOD.values:
            start = get_start_date_for_time_period(time_period)
            self.filter(time_period=time_period).update(
                sender_count=Coalesce(Subquery(
                    self.profile_class.objects.filter(
                        id=OuterRef('prisoner_profile_id'),
                    ).annotate(
                        sender_count=Count(
                            'credits__sender_profile',
                            filter=Q(
                                credits__received_at__gte=start,
                            ),
                            distinct=True
                        )
                    ).values('sender_count')[:1]
                ), 0)
            )

    def update_recipient_counts(self):
        for time_period in TIME_PERIOD.values:
            start = get_start_date_for_time_period(time_period)
            self.filter(time_period=time_period).update(
                recipient_count=Coalesce(Subquery(
                    self.profile_class.objects.filter(
                        id=OuterRef('prisoner_profile_id'),
                    ).annotate(
                        recipient_count=Count(
                            'disbursements__recipient_profile',
                            filter=Q(
                                disbursements__created__gte=start,
                            ),
                            distinct=True
                        )
                    ).values('recipient_count')[:1]
                ), 0)
            )

    def update_all_totals_for_credit(self):
        self.update_credit_counts()
        self.update_credit_totals()
        self.update_sender_counts()

    def update_all_totals_for_disbursement(self):
        self.update_disbursement_counts()
        self.update_disbursement_totals()
        self.update_recipient_counts()

    def update_all_totals(self):
        self.update_all_totals_for_credit()
        self.update_all_totals_for_disbursement()
