import datetime
from datetime import timezone

from django.utils.dateformat import format as format_date

from credit.tests.test_views.test_credit_list import CreditListTestCase


class CreditListWithReceivedAtFilterTestCase(CreditListTestCase):
    def _format_date(self, date):
        return format_date(date, 'Y-m-d')

    def test_filter_received_at_yesterday(self):
        """
        Returns all credits received yesterday
        """
        yesterday = self._get_latest_date()
        self._test_response_with_filters({
            'received_at__gte': self._format_date(yesterday),
            'received_at__lt': self._format_date(yesterday + datetime.timedelta(days=1)),
        })

    def test_filter_received_since_five_days_ago(self):
        """
        Returns all credits received since 5 days ago
        """
        five_days_ago = self._get_latest_date() - datetime.timedelta(days=5)
        self._test_response_with_filters({
            'received_at__gte': self._format_date(five_days_ago),
        })

    def test_filter_received_until_five_days_ago(self):
        """
        Returns all credits received until 5 days ago
        """
        five_days_ago = self._get_latest_date() - datetime.timedelta(days=4)
        self._test_response_with_filters({
            'received_at__lt': self._format_date(five_days_ago),
        })

    def test_filter_received_at_datetimes(self):
        """
        Returns all credits received between two time
        """
        start_date = datetime.datetime.combine(
            self._get_latest_date() - datetime.timedelta(days=2),
            datetime.time(10, 0, tzinfo=timezone.utc)
        )
        end_date = datetime.datetime.combine(
            self._get_latest_date(),
            datetime.time(22, 0, tzinfo=timezone.utc)
        )

        self._test_response_with_filters({
            'received_at__gte': start_date.isoformat(),
            'received_at__lt': end_date.isoformat(),
        })
