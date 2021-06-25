"""
Updates the aggregated, weekly, performance data
"""

import datetime

from django.core.management import BaseCommand, CommandError
from django.db import models
from django.db.models.functions import TruncWeek
from django.utils.dateparse import parse_date

from credit.models import Credit
from performance.models import DigitalTakeup, PerformanceData, UserSatisfaction


class Command(BaseCommand):
    """
    Updates the PerformanceData table by aggregating values from other tables
    """

    def add_arguments(self, parser):
        super().add_arguments(parser)

        parser.add_argument(
            '--week-from',
            help='Performance data from this week (inclusive) will be updated',
            required=True,
        )
        parser.add_argument(
            '--week-to',
            help='Performance data up to this week (exclusive) will be updated',
            required=True,
        )

    def handle(self, *args, **options):
        self.week_from = week_argument(options['week_from'])
        self.week_to = week_argument(options['week_to'])
        if self.week_from >= self.week_to:
            raise CommandError('"--week-from" must be before "--week-to"')

        self._update_credits_by_mtp()
        self._update_digital_takeup()
        self._update_credits_total()
        self._update_user_satisfaction_values()

    def _update_credits_by_mtp(self):
        """
        For each week, counts how many credits have been received (via MTP)
        """

        queryset = Credit.objects \
            .filter(received_at__date__gte=self.week_from, received_at__date__lt=self.week_to) \
            .credited() \
            .order_by() \
            .annotate(week=TruncWeek('received_at')) \
            .values('week') \
            .annotate(credits_by_mtp=models.Count('*'))

        for record in queryset:
            PerformanceData.objects.update_or_create(
                defaults=record,
                week=record['week'],
            )

    def _update_digital_takeup(self):
        """
        Digital take-up but aggregated by week
        """

        week = self.week_from
        while week < self.week_to:
            next_week = week + datetime.timedelta(weeks=1)
            digital_takeup = DigitalTakeup.objects \
                .filter(date__gte=week, date__lt=next_week) \
                .mean_digital_takeup()

            if digital_takeup:
                PerformanceData.objects.update_or_create(
                    defaults={'digital_takeup': digital_takeup},
                    week=week,
                )

            week = next_week

    def _update_credits_total(self):
        """
        Uses the digital take-up percentage to estimate the total number of credits (including by post)

        The credits_total is scaled/extrapolated given:
        1. we know the accurate credits_by_mtp (digital)
        2. we know the percentage of digital transactions (digital_takeup)
        3. digital_takeup = credits_by_mtp / credits_total

        Given 3. credits_total = credits_by_mtp / digital_takeup
        """

        PerformanceData.objects \
            .filter(week__gte=self.week_from, week__lt=self.week_to) \
            .update(credits_total=models.F('credits_by_mtp') / models.F('digital_takeup'))

    def _update_user_satisfaction_values(self):
        """
        Sum user satisfaction ratings by week/calculate user satisfaction percentage

        The user_satisfaction value is the percentage of users 'Satisfied' or 'Very satisfied',
        consistently to what we have in the User Satisfaction report.
        """

        rating_field_names = UserSatisfaction.rating_field_names

        # Get daily data from UserSatisfaction model, in the week from-to range,
        # group by week (TruncWekek), and sum all the ratings frequencies for that week
        queryset = UserSatisfaction.objects \
            .filter(date__gte=self.week_from, date__lt=self.week_to) \
            .order_by() \
            .annotate(week=TruncWeek('date')) \
            .values('week') \
            .annotate(**{
                field: models.Sum(field)
                for field in rating_field_names
            }) \
            .values('week', *rating_field_names) \
            .order_by('week')

        for record in queryset:
            user_satisfaction = None
            rating_field_values = [record[rating_field] for rating_field in rating_field_names]
            total = sum(rating_field_values)
            if total > 0:
                # Percentage of users 'Satisfied' or 'Very satisfied'
                user_satisfaction = (record['rated_4'] + record['rated_5']) / total

            PerformanceData.objects.update_or_create(
                defaults={
                    **record,
                    'user_satisfaction': user_satisfaction,
                },
                week=record['week'],
            )


def week_argument(argument):
    """
    Parse the date argument and returns the Monday of the same week

    Examples:
      '2021-06-25' (Friday) => datetime.date(2021, 6, 21) (Monday)
      '2021-06-28' (Monday) => datetime.date(2021, 6, 28) (Monday)
    """

    if not argument:
        raise CommandError('Dates required')

    date = parse_date(argument)
    if not date:
        raise CommandError('Cannot parse date')

    year, week, _ = date.isocalendar()
    monday = datetime.date.fromisocalendar(year, week, 1)  # 1 = Monday
    return monday
