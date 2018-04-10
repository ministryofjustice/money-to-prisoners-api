import datetime
import itertools

from django.db import models
from django.db.models.expressions import RawSQL
from django.utils.translation import gettext_lazy as _

from core import mean


class DigitalTakeupQueryset(models.QuerySet):
    def digital_takeup(self):
        """
        Add a pre-calculated digital take-up field
        :return: DigitalTakeupQueryset
        """
        return self.annotate(digital_takeup=RawSQL('''
            CASE WHEN credits_by_post + credits_by_mtp > 0
            THEN credits_by_mtp / (credits_by_post + credits_by_mtp)::real
            ELSE NULL END
        ''', ()))

    def digital_takeup_per_day(self):
        """
        Per-day digital take-up averages
        :return: generator
        """
        values = self.digital_takeup().exclude(digital_takeup__isnull=True) \
            .values('date', 'digital_takeup').order_by('date')
        for date, group in itertools.groupby(values, key=lambda value: value['date']):
            yield {
                'date': date,
                'digital_takeup_per_day': mean(value['digital_takeup'] for value in group),
            }

    def mean_digital_takeup(self):
        """
        Get averaged digital take-up
        :return: float
        """
        aggregates = self.aggregate(
            sum_credits_by_post=models.Sum('credits_by_post'),
            sum_credits_by_mtp=models.Sum('credits_by_mtp'),
        )
        try:
            return aggregates['sum_credits_by_mtp'] / (aggregates['sum_credits_by_post'] +
                                                       aggregates['sum_credits_by_mtp'])
        except (ZeroDivisionError, TypeError):
            return None


class DigitalTakeup(models.Model):
    date = models.DateField()
    prison = models.ForeignKey('prison.Prison', on_delete=models.CASCADE)
    credits_by_post = models.IntegerField(verbose_name=_('Credits by post'))
    credits_by_mtp = models.IntegerField(verbose_name=_('Credits sent digitally'))
    amount_by_post = models.IntegerField(verbose_name=_('Amount by post'), null=True)
    amount_by_mtp = models.IntegerField(verbose_name=_('Amount sent digitally'), null=True)

    objects = DigitalTakeupQueryset.as_manager()

    class Meta:
        unique_together = ('date', 'prison')
        ordering = ('date',)
        get_latest_by = 'date'
        verbose_name = verbose_name_plural = _('digital take-up')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._digital_takeup = NotImplemented

    def __str__(self):
        return '%s %s' % (self.date, self.prison_id)

    @property
    def credits_total(self):
        return self.credits_by_post + self.credits_by_mtp

    @property
    def amount_total(self):
        try:
            return self.amount_by_post + self.amount_by_mtp
        except TypeError:
            pass

    @property
    def digital_takeup(self):
        if self._digital_takeup is NotImplemented:
            credits_total = self.credits_total
            self._digital_takeup = self.credits_by_mtp / credits_total if credits_total > 0 else None
        return self._digital_takeup

    @digital_takeup.setter
    def digital_takeup(self, value):
        # to support pre-calculating take-up on the queryset
        self._digital_takeup = value

    @property
    def formatted_digital_takeup(self):
        digital_takeup = self.digital_takeup
        if digital_takeup is None:
            return '–'
        return '%0.0f%%' % (digital_takeup * 100)


class PredictedPostalCredits:
    """
    Credit reports from NOMIS are not always provided for every day of crediting, so the DigitalTakeup model
    underestimates the amount of credits received by post.
    Assuming that the mean digital take-up over a week or more is accurate,
    then the postal credits can be predicted knowing what was credited online.

    https://docs.google.com/spreadsheets/d/17NmJ1AE1xnvPUcKW-LoYfc6_uNdvr5fBapd5mjV3jyw/
    https://docs.google.com/spreadsheets/d/1-NHn7rza-UCU86tJN1-dDgZ-hFzSLt_xi4ESzySfUrI/
    https://docs.google.com/spreadsheets/d/1dYqr0NMd8W5LZRTNdIC-AjyHLEy6khRpS0xFAh6B_z0/
    https://docs.google.com/spreadsheets/d/1jQ5kP_b55aZovMDrTo7054_Hjxs6K4b1VZibTbzwdso/
    """

    def __init__(self, from_date=None, to_date=None):
        from credit.models import Credit, CREDIT_RESOLUTION

        self.credit_queryset = Credit.objects.filter(resolution=CREDIT_RESOLUTION.CREDITED)
        if not from_date:
            from_date = DigitalTakeup.objects.earliest().date
        if not to_date:
            to_date = DigitalTakeup.objects.latest().date
        self.from_date = from_date
        self.to_date = to_date

    def all(self):
        return self.predict_interval(self.from_date, self.to_date)

    def monthly(self):
        start_date = self.from_date.replace(day=1)
        while start_date <= self.to_date:
            if start_date.month == 12:
                end_date = datetime.date(start_date.year + 1, 1, 1)
            else:
                end_date = datetime.date(start_date.year, start_date.month + 1, 1)
                yield self.predict_interval(start_date, end_date)
            start_date = end_date

    def weekly(self):
        start_date = self.from_date - datetime.timedelta(days=self.from_date.weekday())
        while start_date <= self.to_date:
            end_date = start_date + datetime.timedelta(days=7)
            yield self.predict_interval(start_date, end_date)
            start_date = end_date

    def predict_interval(self, start_date, end_date):
        reported = DigitalTakeup.objects.filter(
            date__gte=start_date,
            date__lt=end_date,
        ).aggregate(
            credits_by_post=models.Sum('credits_by_post'),
            credits_by_mtp=models.Sum('credits_by_mtp'),
            amount_by_post=models.Sum('amount_by_post'),
            amount_by_mtp=models.Sum('amount_by_mtp'),
        )
        if not reported['credits_by_mtp']:
            return None
        post_ratio = reported['credits_by_post'] / reported['credits_by_mtp']
        if not reported['amount_by_mtp'] or not reported['credits_by_post']:
            # historically amount was not stored, assume post and digital have same average amount
            post_amount_ratio = 1
        else:
            post_amount_ratio = (
                (reported['amount_by_post'] * reported['credits_by_mtp']) /
                (reported['amount_by_mtp'] * reported['credits_by_post'])
            )

        data = self.credit_queryset.filter(
            received_at__date__gte=start_date,
            received_at__date__lt=end_date,
        ).aggregate(
            credits_by_mtp=models.Count('id'),
            amount_by_mtp=models.Sum('amount'),
        )
        data.update(
            reported_credits_by_post=reported['credits_by_post'],
            reported_amount_by_post=reported['amount_by_post'],
            predicted_credits_by_post=int(data['credits_by_mtp'] * post_ratio),
            predicted_amount_by_post=int(data['amount_by_mtp'] * post_amount_ratio * post_ratio),
            start_date=start_date,
            end_date=end_date,
        )
        return data
