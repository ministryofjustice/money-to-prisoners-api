import datetime

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from core.utils import monday_of_same_week
from credit.constants import CreditResolution
from credit.models import Credit
from model_bakery import baker
from performance.models import DigitalTakeup, PerformanceData, UserSatisfaction
from prison.models import Prison


class UpdatePerformanceDataTestTestCase(TestCase):

    def test_update_credits_by_mtp(self):
        test_data = [
            # +-----+-----------------------------+
            # | Day | Number of credits to create |
            # +-----+-----------------------------+
            (datetime.date(2020, 12, 28), 10),  # Monday
            (datetime.date(2020, 12, 29), 20),
            (datetime.date(2020, 12, 30), 30),
            (datetime.date(2020, 12, 31), 40),
            (datetime.date(2021, 1, 1), 50),
            (datetime.date(2021, 1, 2), 60),
            (datetime.date(2021, 1, 3), 70),   # Sunday
            (datetime.date(2021, 1, 4), 111),  # (some credits outside range follow)
            (datetime.date(1999, 7, 4), 111),  # before range
            (datetime.date(3333, 2, 2), 111),  # after range
        ]
        for day, credits_count in test_data:
            day_with_time = datetime.datetime.combine(day, datetime.time.min)
            day_with_time = timezone.make_aware(day_with_time)

            baker.make(
                Credit,
                received_at=day_with_time,
                resolution=CreditResolution.credited,
                _quantity=credits_count,
            )
            # Also create a PENDING credit per day (to test ignored credits)
            baker.make(
                Credit,
                received_at=day_with_time,
                resolution=CreditResolution.pending,
                _quantity=1,
            )

        monday = datetime.date(2020, 12, 28)
        performance_data = PerformanceData.objects.filter(week=monday)

        self.assertFalse(performance_data.exists())

        call_command(
            'update_performance_data',
            week_from='2021-01-02',
            week_to='2021-01-05',
        )

        self.assertTrue(
            performance_data.exists(),
            f'PerformanceData record for week commencing {monday} not created'
        )
        record = performance_data.first()
        expected_credits_by_mtp = 10+20+30+40+50+60+70
        self.assertEqual(record.credits_by_mtp, expected_credits_by_mtp)

    def test_update_digital_takeup(self):
        prison_1 = baker.make(Prison, name='Prison 1')
        prison_2 = baker.make(Prison, name='Prison 2')

        test_data = [
            # +-----+--------+----------------+-----------------+
            # | Day | Prison | Credits by MTP | Credits by post |
            # +-----+--------+----------------+-----------------+
            (datetime.date(2020, 12, 28), prison_1, 99, 1),  # Monday
            (datetime.date(2020, 12, 29), prison_1, 90, 10),
            (datetime.date(2020, 12, 30), prison_1, 98, 2),
            (datetime.date(2020, 12, 31), prison_1, 95, 5),
            (datetime.date(2021, 1, 1),   prison_1, 85, 0),
            (datetime.date(2021, 1, 2),   prison_1, 90, 1),
            (datetime.date(2021, 1, 3),   prison_1, 200, 6),  # Sunday
            (datetime.date(2020, 12, 28), prison_2, 100, 2),  # Monday
            (datetime.date(2020, 12, 29), prison_2, 200, 4),
            (datetime.date(2020, 12, 30), prison_2, 500, 8),
            (datetime.date(2020, 12, 31), prison_2, 1500, 16),
            (datetime.date(2021, 1, 1),   prison_2, 2222, 32),
            (datetime.date(2021, 1, 2),   prison_2, 4800, 64),
            (datetime.date(2021, 1, 3),   prison_2, 2345, 128),  # Sunday
        ]
        for day, prison, by_mtp, by_post in test_data:
            baker.make(
                DigitalTakeup,
                date=day,
                prison=prison,
                credits_by_mtp=by_mtp,
                credits_by_post=by_post,
            )

        record = PerformanceData.objects.create(
            week=datetime.date(2020, 12, 28),
            user_satisfaction=0.95,
        )

        call_command(
            'update_performance_data',
            week_from='2020-12-31',
            week_to='2021-01-10',
        )

        record.refresh_from_db()

        # All credits received by MTP regardless of prison
        week_credits_by_mtp = (99+90+98+95+85+90+200) + (100+200+500+1500+2222+4800+2345)
        # All credits received by post regardless of prison
        week_credits_by_post = (1+10+2+5+0+1+6) + (2+4+8+16+32+64+128)
        week_credits_total = week_credits_by_mtp + week_credits_by_post
        expected_digital_takeup = week_credits_by_mtp / week_credits_total
        self.assertAlmostEqual(record.digital_takeup, expected_digital_takeup)

        # It doesn't change existing PerformanceData values
        self.assertAlmostEqual(record.user_satisfaction, 0.95)

    def test_update_credits_total(self):
        test_data = [
            # +-----+----------------+------------------+----------------+
            # | Week | Credits by MTP | Digital Take-up | Expected total |
            # +-----+----------------+------------------+----------------+
            (datetime.date(2020, 12, 28), 90, 0.90, 100),
            (datetime.date(2021, 1, 4), None, None, None),
            (datetime.date(2021, 1, 11), 90, None, None),
            (datetime.date(2021, 1, 18), None, 0.90, None),
            (datetime.date(2021, 1, 25), 91, 0.934, 97),  # Round down
            (datetime.date(2021, 2, 1), 92, 0.97, 95),    # Round up
        ]
        for (week, by_mtp, takeup, _) in test_data:
            baker.make(
                PerformanceData,
                week=week,
                credits_by_mtp=by_mtp,
                digital_takeup=takeup,
            )

        # NOTE: This will update weeks from Mon 28th December 2020 to
        # Mon 8th February 2021 (not included). So last weekly record updated
        # will be the one for the week commencing Mon 1st February 2021
        call_command(
            'update_performance_data',
            week_from='2020-12-31',
            week_to='2021-02-10',
        )

        for (week, by_mtp, takeup, expected_total) in test_data:
            record = PerformanceData.objects.get(week=week)

            # Check existing values didn't change
            self.assertEqual(record.credits_by_mtp, by_mtp)
            self.assertAlmostEqual(record.digital_takeup, takeup)

            self.assertEqual(record.credits_total, expected_total)

    def test_update_user_satisfaction_values(self):
        test_data = [
            # +-----+--------------------------+
            # | Day | List with rated_* values |
            # +-----+--------------------------+
            (datetime.date(2020, 12, 28), [1, 2, 1, 2, 0]),  # Monday
            (datetime.date(2020, 12, 29), [1, 1, 0, 2, 10]),
            (datetime.date(2020, 12, 30), [0, 0, 0, 4, 5]),
            (datetime.date(2020, 12, 31), [0, 0, 5, 10, 3]),
            (datetime.date(2021, 1, 1),   [0, 0, 0, 6, 11]),
            (datetime.date(2021, 1, 2),   [0, 0, 0, 7, 10]),
            (datetime.date(2021, 1, 3),   [0, 0, 0, 4, 5]),  # Sunday
            (datetime.date(2021, 1, 4),   [9, 9, 9, 9, 9]),  # (outside range)
        ]
        for day, ratings in test_data:
            UserSatisfaction.objects.create(date=day, **{
                f'rated_{i + 1}': rating
                for i, rating in enumerate(ratings)
            })

        call_command(
            'update_performance_data',
            week_from='2020-12-28',
            week_to='2021-01-04',
        )

        record = PerformanceData.objects.get(week='2020-12-28')

        sum_rated_1 = (1+1+0+0+0+0+0)
        sum_rated_2 = (2+1+0+0+0+0+0)
        sum_rated_3 = (1+0+0+5+0+0+0)
        sum_rated_4 = (2+2+4+10+6+7+4)
        sum_rated_5 = (0+10+5+3+11+10+5)
        self.assertEqual(record.rated_1, sum_rated_1)
        self.assertEqual(record.rated_2, sum_rated_2)
        self.assertEqual(record.rated_3, sum_rated_3)
        self.assertEqual(record.rated_4, sum_rated_4)
        self.assertEqual(record.rated_5, sum_rated_5)

        total_ratings = sum_rated_1+sum_rated_2+sum_rated_3+sum_rated_4+sum_rated_5
        expected_user_satisfaction = (sum_rated_4+sum_rated_5) / total_ratings
        self.assertAlmostEqual(record.user_satisfaction, expected_user_satisfaction)

    def test_default_range(self):
        # Create some records in the last month
        day = timezone.localdate() - datetime.timedelta(days=30)
        while day <= timezone.localdate():
            UserSatisfaction.objects.create(date=day, **{
                f'rated_{i + 1}': rating
                for i, rating in enumerate([1, 2, 3, 4, 5])
            })

            day = day + datetime.timedelta(days=1)

        self.assertEqual(PerformanceData.objects.count(), 0)

        call_command('update_performance_data')

        # Check only record for the correct week was created
        self.assertEqual(PerformanceData.objects.count(), 1)

        monday = monday_of_same_week(timezone.localdate())
        monday_two_weeks_ago = monday - datetime.timedelta(weeks=2)
        self.assertTrue(PerformanceData.objects.filter(week=monday_two_weeks_ago).exists())

    def test_invalid_arguments(self):
        with self.assertRaises(CommandError, msg='Cannot parse date'):
            call_command('update_performance_data', week_from='foo', week_to='2021-12-31')

        with self.assertRaises(CommandError, msg='Must provide both --week-from/--week-to or not provide them'):
            call_command('update_performance_data', week_from='2021-01-01')

        with self.assertRaises(CommandError, msg='Must provide both --week-from/--week-to or not provide them'):
            call_command('update_performance_data', week_to='2021-12-31')

        with self.assertRaises(CommandError, msg='"--week-from" must be before "--week-to"'):
            call_command('update_performance_data', week_from='2021-01-10', week_to='2021-01-01')
