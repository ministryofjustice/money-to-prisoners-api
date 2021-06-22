import datetime
import itertools

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import connection, models
from django.db.models.expressions import RawSQL
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core import dictfetchall, mean
from core.models import validate_monday


class DigitalTakeupManager(models.Manager):
    def digital_takeup_per_month(self, since=None, exclude_private_estate=False):
        """
        Per-month digital take-up averages
        """
        if since is None:
            today = timezone.localdate()
            since = max(DigitalTakeup.reports_start, today.replace(year=today.year - 2, month=1, day=1))

        if exclude_private_estate:
            included_prisons_sql = """
                included_prisons AS (
                    SELECT prison_prison.nomis_id as nomis_id
                    FROM prison_prison
                    WHERE prison_prison.private_estate IS false
                ),
            """
            credit_count_join_sql = """
                JOIN included_prisons ON included_prisons.nomis_id = credit_credit.prison_id
            """
            average_takeup_join_sql = """
                JOIN included_prisons ON included_prisons.nomis_id = performance_digitaltakeup.prison_id
            """
        else:
            included_prisons_sql = ''
            credit_count_join_sql = ''
            average_takeup_join_sql = ''

        sql = f"""
        WITH
            {included_prisons_sql}
            credit_count AS (
                SELECT
                    date_trunc('month', received_at AT TIME ZONE '{settings.TIME_ZONE}')::timestamp WITH TIME ZONE
                        AS date,
                    COUNT(*) AS accurate_credits_by_mtp
                FROM credit_credit
                {credit_count_join_sql}
                WHERE resolution = 'credited' AND received_at >= %(since)s
                GROUP BY date_trunc('month', received_at AT TIME ZONE '{settings.TIME_ZONE}')
            ),
            average_takeup AS (
                SELECT date_trunc('month', date) AS date,
                    SUM(credits_by_post) AS reported_credits_by_post,
                    SUM(credits_by_mtp) AS reported_credits_by_mtp
                FROM performance_digitaltakeup
                {average_takeup_join_sql}
                WHERE date >= %(since)s
                GROUP BY date_trunc('month', date)
            )
        SELECT credit_count.date, accurate_credits_by_mtp, reported_credits_by_post, reported_credits_by_mtp
        FROM credit_count
        FULL OUTER JOIN average_takeup ON credit_count.date = average_takeup.date
        ORDER BY credit_count.date
        """

        with connection.cursor() as cursor:
            cursor.execute(sql, params={'since': since})
            return dictfetchall(cursor)


class DigitalTakeupQueryset(models.QuerySet):
    def digital_takeup(self):
        """
        Add a pre-calculated digital take-up field
        :return: DigitalTakeupQueryset
        """
        return self.annotate(digital_takeup=RawSQL("""
            CASE WHEN credits_by_post + credits_by_mtp > 0
            THEN credits_by_mtp / (credits_by_post + credits_by_mtp)::real
            ELSE NULL END
        """, ()))

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

    objects = DigitalTakeupManager.from_queryset(DigitalTakeupQueryset)()

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


class UserSatisfactionQueryset(models.QuerySet):
    def percentage_satisfied(self):
        """
        Add a pre-calculated per-day percentage of responses that were satisfied or very satisfied
        :return: UserSatisfactionQueryset
        """
        return self.annotate(percentage_satisfied=RawSQL("""
            CASE WHEN (rated_1 + rated_2 + rated_3 + rated_4 + rated_5) > 0
            THEN (rated_4 + rated_5) / (rated_1 + rated_2 + rated_3 + rated_4 + rated_5)::real
            ELSE NULL END
        """, ()))

    def mean_percentage_satisfied(self):
        """
        Get averaged percentage of responses that were satisfied or very satisfied from whole queryset range
        :return: float
        """
        aggregates = self.aggregate(
            sum_rated_1=models.Sum('rated_1'),
            sum_rated_2=models.Sum('rated_2'),
            sum_rated_3=models.Sum('rated_3'),
            sum_rated_4=models.Sum('rated_4'),
            sum_rated_5=models.Sum('rated_5'),
        )
        try:
            return (aggregates['sum_rated_4'] + aggregates['sum_rated_5']) / sum(aggregates.values())
        except (ZeroDivisionError, TypeError):
            return None


class UserSatisfaction(models.Model):
    """
    The number of responses for each rating per day as provided by the Feedback Explorer export on GOV.UK publishing
    """
    date = models.DateField(primary_key=True)
    rated_1 = models.PositiveIntegerField(verbose_name=_('Very dissatisfied'))
    rated_2 = models.PositiveIntegerField(verbose_name=_('Dissatisfied'))
    rated_3 = models.PositiveIntegerField(verbose_name=_('Neither satisfied or dissatisfied'))
    rated_4 = models.PositiveIntegerField(verbose_name=_('Satisfied'))
    rated_5 = models.PositiveIntegerField(verbose_name=_('Very satisfied'))
    rating_field_names = [f'rated_{rating}' for rating in range(1, 6)]

    objects = models.Manager.from_queryset(UserSatisfactionQueryset)()

    reports_start = datetime.date(2016, 11, 15)

    class Meta:
        ordering = ('date',)
        get_latest_by = 'date'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._percentage_satisfied = NotImplemented

    @property
    def all_ratings(self):
        return self.rated_1, self.rated_2, self.rated_3, self.rated_4, self.rated_5

    @property
    def percentage_satisfied(self):
        if self._percentage_satisfied is NotImplemented:
            count = sum(self.all_ratings)
            self._percentage_satisfied = (self.rated_4 + self.rated_5) / count if count > 0 else None
        return self._percentage_satisfied

    @percentage_satisfied.setter
    def percentage_satisfied(self, value):
        # to support pre-calculating percentage on the queryset
        self._percentage_satisfied = value


class PerformanceData(models.Model):
    """
    Weekly performance data
    """

    # Monday of that week
    week = models.DateField(primary_key=True, verbose_name='Week commencing', validators=[validate_monday])

    # Digital Take-up data
    credits_total = models.PositiveIntegerField(verbose_name='Transactions – total', null=True, blank=True)
    credits_by_mtp = models.PositiveIntegerField(verbose_name='Transactions – online', null=True, blank=True)
    digital_takeup = models.FloatField(
        verbose_name='Digital take-up',
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )

    # Completion rate, taken from Google Analytics/Google Data Studio
    completion_rate = models.FloatField(
        verbose_name='Completion rate',
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )

    # User satisfaction data, weekly aggregation from UserSatisfaction model
    user_satisfaction = models.FloatField(
        verbose_name=_('User satisfaction'),
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    rated_1 = models.PositiveIntegerField(verbose_name=_('Very dissatisfied'), null=True, blank=True)
    rated_2 = models.PositiveIntegerField(verbose_name=_('Dissatisfied'), null=True, blank=True)
    rated_3 = models.PositiveIntegerField(verbose_name=_('Neither satisfied or dissatisfied'), null=True, blank=True)
    rated_4 = models.PositiveIntegerField(verbose_name=_('Satisfied'), null=True, blank=True)
    rated_5 = models.PositiveIntegerField(verbose_name=_('Very satisfied'), null=True, blank=True)
    rating_field_names = [f'rated_{rating}' for rating in range(1, 6)]

    class Meta:
        ordering = ('week',)
        get_latest_by = 'week'
        verbose_name = verbose_name_plural = _('Performance data')
