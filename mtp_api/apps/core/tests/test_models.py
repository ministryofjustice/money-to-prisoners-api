import datetime

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from core.models import validate_monday


class TestValidateMonday(SimpleTestCase):
    """
    Tests for validate_monday validator
    """

    def test_when_not_monday_raises_validation_error(self):
        date = datetime.date(2021, 6, 22)  # Tuesday
        with self.assertRaises(ValidationError):
            validate_monday(date)

    def test_when_monday_doesnt_raise_error(self):
        date = datetime.date(2021, 6, 21)  # Monday
        validate_monday(date)
