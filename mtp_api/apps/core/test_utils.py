import datetime
from django.test.testcases import SimpleTestCase

from core.utils import monday_of_same_week


class MondayOfSameWeekTestCase(SimpleTestCase):

    def test_monday_of_same_week(self):
        test_data = [
            (datetime.date(2021, 7, 12), datetime.date(2021, 7, 12)),  # a monday
            (datetime.date(2021, 7, 30), datetime.date(2021, 7, 26)),  # another day
            (datetime.date(2021, 1, 1), datetime.date(2020, 12, 28)),  # crossing years
        ]
        for (day, expected) in test_data:
            result = monday_of_same_week(day)
            self.assertEqual(result, expected)
