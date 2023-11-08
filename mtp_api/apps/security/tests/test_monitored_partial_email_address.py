from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from security.models import MonitoredPartialEmailAddress


class MonitoredPartialEmailAddressTestCase(TestCase):
    def setUp(self):
        MonitoredPartialEmailAddress.objects.create(keyword='some')
        self.sample_model = MonitoredPartialEmailAddress.objects.create(keyword='bad')
        MonitoredPartialEmailAddress.objects.create(keyword='words')

    def test_unique(self):
        with self.assertRaises(IntegrityError):
            MonitoredPartialEmailAddress.objects.create(keyword='some')

    def test_min_length(self):
        with self.assertRaises(ValidationError):
            model = MonitoredPartialEmailAddress(keyword='1')
            model.full_clean()

    def test_matching_email_address(self):
        self.assertTrue(self.sample_model.matches('very-bad@mail.local'))
        self.assertTrue(MonitoredPartialEmailAddress.objects.is_email_address_monitored('very-bad@mail.local'))

        self.assertTrue(self.sample_model.matches('also-Bad@mail.local'))
        self.assertTrue(MonitoredPartialEmailAddress.objects.is_email_address_monitored('also-Bad@mail.local'))

    def test_non_matching_email_address(self):
        self.assertFalse(self.sample_model.matches('super-good@mail.local'))
        self.assertFalse(MonitoredPartialEmailAddress.objects.is_email_address_monitored('super-good@mail.local'))
