import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.dateformat import format as date_format
from django.utils.timezone import make_aware
from model_mommy import mommy
from oauth2_provider.models import Application

from mtp_auth.models import Login, PrisonUserMapping
from mtp_auth.views import LoginStatsView
from prison.models import Prison

User = get_user_model()


class LoginCountTestCase(TestCase):
    def login(self, user, application, date):
        now = make_aware(datetime.datetime(*date, 12))
        with mock.patch('django.db.models.fields.timezone.now', return_value=now):
            Login.objects.create(
                user=user,
                application=application,
            )

    def test_login_counts(self):
        application = Application.objects.create(
            client_id='test-app',
            client_secret='test-app',
            client_type='confidential',
            authorization_grant_type='password',
            name='Test App',
            user=mommy.make(User),
        )
        prison = mommy.make(Prison, nomis_id='ABC')
        user_in_prison = mommy.make(User)
        another_user_in_prison = mommy.make(User)
        mommy.make(PrisonUserMapping, user=user_in_prison, prisons=[prison])
        mommy.make(PrisonUserMapping, user=another_user_in_prison, prisons=[prison])
        user_not_in_prison = mommy.make(User)

        # last month: 3 login in prison
        self.login(user_in_prison, application, (2018, 3, 10))
        self.login(another_user_in_prison, application, (2018, 3, 17))
        self.login(user_in_prison, application, (2018, 3, 28))
        # this month: 2 logins in prison, 1 not linked to a prison
        self.login(user_in_prison, application, (2018, 4, 10))
        self.login(another_user_in_prison, application, (2018, 4, 11))
        self.login(user_not_in_prison, application, (2018, 4, 10))

        now = make_aware(datetime.datetime(2018, 4, 15, 12))
        with mock.patch('mtp_auth.views.timezone.localtime', return_value=now):
            view = LoginStatsView()
            current_month_progress, months = view.current_month_progress, view.months

        # "today" midday is roughly half way through April
        self.assertAlmostEqual(current_month_progress, 0.5, delta=0.02)

        this_month, last_month, *_ = months
        this_month = date_format(this_month, 'Y-m')
        last_month = date_format(last_month, 'Y-m')

        login_counts = view.get_login_counts(application.client_id)

        # expect there to be double by the end of the month
        self.assertEqual(login_counts[(prison.nomis_id, this_month)], 4)
        self.assertEqual(login_counts[(None, this_month)], 2)
        self.assertEqual(login_counts[(prison.nomis_id, last_month)], 3)
        self.assertEqual(login_counts[(None, last_month)], 0)
