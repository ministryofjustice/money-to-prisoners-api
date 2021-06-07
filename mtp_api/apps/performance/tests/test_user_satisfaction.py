import datetime
import pathlib

from django.test import TestCase
from django.core.files.base import File

from performance.forms import UserSatisfactionUploadForm
from performance.models import UserSatisfaction


class UserSatisfactionTestCase(TestCase):
    fixtures = ['initial_types']

    def test_calculate_takeup(self):
        self.assertIsNone(UserSatisfaction.objects.mean_percentage_satisfied())

        test_data = [
            (datetime.date(2021, 4, 29), [0, 0, 1, 2, 3]),
            (datetime.date(2021, 4, 30), [1, 1, 0, 2, 10]),
            (datetime.date(2021, 5, 1), [0, 0, 0, 4, 5]),
            (datetime.date(2021, 5, 2), [0, 0, 5, 10, 3]),
        ]
        for date, ratings in test_data:
            UserSatisfaction.objects.create(date=date, **{
                f'rated_{i + 1}': rating
                for i, rating in enumerate(ratings)
            })

        # test queryset aggregate method
        self.assertAlmostEqual(
            UserSatisfaction.objects.mean_percentage_satisfied(),
            (2 + 3 + 2 + 10 + 4 + 5 + 10 + 3) / (1 + 2 + 3 + 1 + 1 + 2 + 10 + 4 + 5 + 5 + 10 + 3)
        )
        self.assertAlmostEqual(
            UserSatisfaction.objects.filter(date__gte=datetime.date(2021, 5, 1)).mean_percentage_satisfied(),
            (4 + 5 + 10 + 3) / (4 + 5 + 5 + 10 + 3)
        )
        # test model method
        self.assertAlmostEqual(
            UserSatisfaction.objects.get(date=datetime.date(2021, 4, 30)).percentage_satisfied,
            (2 + 10) / (1 + 1 + 2 + 10)
        )
        # test queryset annotation method
        precalculated_queryset = UserSatisfaction.objects \
            .filter(date__lt=datetime.date(2021, 5, 1)) \
            .percentage_satisfied() \
            .values_list('percentage_satisfied', flat=True)
        self.assertSequenceEqual(
            precalculated_queryset,
            [
                (2 + 3) / (1 + 2 + 3),
                (2 + 10) / (1 + 1 + 2 + 10),
            ]
        )


class UserSatisfactionUploadTestCase(TestCase):
    fixtures = ['initial_types']
    path = pathlib.Path(__file__).parent / 'files'

    def upload_test_file(self, file_name):
        path = self.path / file_name
        with File(path.open('rb')) as f:
            form = UserSatisfactionUploadForm(data={}, files={'csv_file': f})
            self.assertTrue(form.is_valid(), msg=f'{file_name} should be a valid csv except: {form.errors.as_text()}')
        form.save()

    def test_mixed_spreadsheet_parsing(self):
        # a typical export includes aggregated user satisfaction ratings mixed in with feedback
        self.assertEqual(UserSatisfaction.objects.all().count(), 0)
        self.upload_test_file('feedex_done_send-prisoner-money - mixed.csv')
        self.assertEqual(UserSatisfaction.objects.count(), 1)
        self.assertSequenceEqual(
            UserSatisfaction.objects.get(pk=datetime.date(2021, 5, 1)).all_ratings,
            [2, 1, 2, 11, 75]
        )

    def assertMultiDaySpreadsheetUploads(self):  # noqa: N802
        self.upload_test_file('feedex_done_send-prisoner-money - multiple days.csv')
        self.assertSequenceEqual(
            UserSatisfaction.objects.get(pk=datetime.date(2021, 5, 1)).all_ratings,
            [2, 1, 2, 11, 75]
        )
        self.assertSequenceEqual(
            UserSatisfaction.objects.get(pk=datetime.date(2021, 5, 2)).all_ratings,
            [1, 1, 1, 6, 68]
        )
        self.assertSequenceEqual(
            UserSatisfaction.objects.get(pk=datetime.date(2021, 5, 3)).all_ratings,
            [0, 1, 0, 11, 67]
        )

    def test_spreadsheet_parsing_with_multiple_days(self):
        # a typical export includes multiple days, but ratings with no responses will not produce a line in the export
        self.assertEqual(UserSatisfaction.objects.all().count(), 0)
        self.assertMultiDaySpreadsheetUploads()
        self.assertEqual(UserSatisfaction.objects.count(), 3)

    def test_overlapping_dates_are_cleared(self):
        # user satisfaction ratings are aggregated by date in the Feedback Explorer so this is used as the primary key
        # when uploading a spreadsheet, existing satisfaction records must be replaced
        UserSatisfaction.objects.create(
            date=datetime.date(2021, 4, 30),
            rated_1=1,
            rated_2=2,
            rated_3=3,
            rated_4=4,
            rated_5=5,
        )
        UserSatisfaction.objects.create(
            date=datetime.date(2021, 5, 2),
            rated_1=5,
            rated_2=4,
            rated_3=3,
            rated_4=2,
            rated_5=1,
        )
        self.assertEqual(UserSatisfaction.objects.all().count(), 2)
        self.assertMultiDaySpreadsheetUploads()
        self.assertEqual(UserSatisfaction.objects.count(), 4)
        self.assertSequenceEqual(
            UserSatisfaction.objects.get(pk=datetime.date(2021, 4, 30)).all_ratings,
            [1, 2, 3, 4, 5]
        )

    def test_invalid_file(self):
        path = self.path / 'Money_to_Prisoner_Stats - 29.01.18.xls'
        with File(path.open('rb')) as f:
            form = UserSatisfactionUploadForm(data={}, files={'csv_file': f})
            self.assertFalse(form.is_valid(), msg='Should not be a valid file')
        self.assertIn('upload a .csv file', form.errors.as_text())

    def test_malformed_csv(self):
        path = self.path / 'feedex_done_send-prisoner-money - malformed.csv'
        with File(path.open('rb')) as f:
            form = UserSatisfactionUploadForm(data={}, files={'csv_file': f})
            self.assertFalse(form.is_valid(), msg='Should not be a valid file')
        self.assertIn('CSV file does not contain the expected structure', form.errors.as_text())
