from django.db import connection, models, transaction
from django.db.models import Count, Sum, Subquery, OuterRef
from django.db.models.functions import Coalesce


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


class SenderProfileManager(models.Manager):
    def get_queryset(self):
        return SenderProfileQuerySet(model=self.model, using=self._db, hints=self._hints)

    def get_anonymous_sender(self):
        return self.get(
            bank_transfer_details__isnull=True,
            debit_card_details__isnull=True
        )


class RecipientProfileManager(models.Manager):
    def get_queryset(self):
        return RecipientProfileQuerySet(model=self.model, using=self._db, hints=self._hints)

    def get_cheque_recipient(self):
        return self.get(
            bank_transfer_details__isnull=True
        )


class PrisonerProfileQuerySet(models.QuerySet):
    def recalculate_totals(self):
        self.recalculate_credit_totals()
        self.recalculate_disbursement_totals()

    def recalculate_credit_totals(self):
        from security.models import PrisonerProfile

        self.update(
            credit_count=Coalesce(Subquery(
                PrisonerProfile.objects.filter(
                    id=OuterRef('id'),
                ).annotate(
                    calculated=Count('credits', distinct=True)
                ).values('calculated')[:1]
            ), 0),
            credit_total=Coalesce(Subquery(
                PrisonerProfile.objects.filter(
                    id=OuterRef('id'),
                ).annotate(
                    calculated=Sum('credits__amount')
                ).values('calculated')[:1]
            ), 0),
        )

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
        from security.models import SenderProfile

        self.update(
            credit_count=Coalesce(Subquery(
                SenderProfile.objects.filter(
                    id=OuterRef('id'),
                ).annotate(
                    calculated=Count('credits', distinct=True)
                ).values('calculated')[:1]
            ), 0),
            credit_total=Coalesce(Subquery(
                SenderProfile.objects.filter(
                    id=OuterRef('id'),
                ).annotate(
                    calculated=Sum('credits__amount')
                ).values('calculated')[:1]
            ), 0),
        )


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
