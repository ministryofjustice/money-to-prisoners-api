import datetime
import itertools

from django.db import connection, models
from django.db.models.expressions import RawSQL
from django.utils.translation import gettext_lazy as _

from core import dictfetchall, mean


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

    def digital_takeup_per_month(self, since=None):
        """
        Per-month digital take-up averages
        :return:  generator
        """
        if since is None:
            today = datetime.date.today()
            since = max(DigitalTakeup.reports_start, today.replace(year=today.year - 2, month=1, day=1))
        with connection.cursor() as cursor:
            cursor.execute('''
                WITH credit_count AS (
                  SELECT date_trunc('month', received_at) AS date,
                    COUNT(*) AS accurate_credits_by_mtp
                  FROM credit_credit
                  WHERE resolution = 'credited' AND received_at >= %(since)s
                  GROUP BY date_trunc('month', received_at)
                ), average_takeup AS (
                  SELECT date_trunc('month', date) AS date,
                    SUM(credits_by_post) AS reported_credits_by_post,
                    SUM(credits_by_mtp) AS reported_credits_by_mtp
                  FROM performance_digitaltakeup
                  WHERE date >= %(since)s
                  GROUP BY date_trunc('month', date)
                )
                SELECT credit_count.date, accurate_credits_by_mtp, reported_credits_by_post, reported_credits_by_mtp
                FROM credit_count FULL OUTER JOIN average_takeup ON credit_count.date = average_takeup.date
                ORDER BY credit_count.date
            ''', params={'since': since})
            return dictfetchall(cursor)

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

    reports_start = datetime.date(2017, 1, 1)

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
