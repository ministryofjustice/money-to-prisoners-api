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
            .values('start_date', 'digital_takeup').order_by('start_date')
        for start_date, group in itertools.groupby(values, key=lambda value: value['start_date']):
            yield {
                'start_date': start_date,
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
    start_date = models.DateField()
    end_date = models.DateField()
    prison = models.ForeignKey('prison.Prison', on_delete=models.CASCADE)
    credits_by_post = models.IntegerField(verbose_name=_('Credits by post'))
    credits_by_mtp = models.IntegerField(verbose_name=_('Credits sent digitally'))

    objects = DigitalTakeupQueryset.as_manager()

    class Meta:
        unique_together = ('start_date', 'end_date', 'prison')
        ordering = ('start_date',)
        get_latest_by = 'start_date'
        verbose_name = verbose_name_plural = _('digital take-up')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._digital_takeup = NotImplemented

    def __str__(self):
        return '%s–%s %s' % (self.start_date, self.end_date, self.prison_id)

    @property
    def credits_total(self):
        return self.credits_by_post + self.credits_by_mtp

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
