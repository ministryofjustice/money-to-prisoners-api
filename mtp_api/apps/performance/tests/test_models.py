import datetime

from django.test import TestCase

from performance.models import DigitalTakeup
from prison.models import Prison


class DigitalUptakeTestCase(TestCase):
    fixtures = ['initial_types', 'test_prisons']

    def test_calculate_takeup(self):
        self.assertIsNone(DigitalTakeup.objects.mean_digital_takeup())
        date = datetime.date(2016, 10, 26)
        prison1 = Prison.objects.get(pk='INP')
        prison2 = Prison.objects.get(pk='IXB')
        DigitalTakeup.objects.create(
            date=date,
            prison=prison1,
            credits_by_post=21,
            credits_by_mtp=13,
        )
        DigitalTakeup.objects.create(
            date=date,
            prison=prison2,
            credits_by_post=19,
            credits_by_mtp=23,
        )
        self.assertAlmostEqual(DigitalTakeup.objects.mean_digital_takeup(), (13 + 23) / (21 + 13 + 19 + 23))
        self.assertAlmostEqual(DigitalTakeup.objects.filter(prison=prison1).mean_digital_takeup(), 13 / (21 + 13))
