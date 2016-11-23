import datetime
import pathlib

from django.test import TestCase
from django.core.files.base import File

from performance.forms import DigitalTakeupUploadForm
from performance.models import DigitalTakeup


class DigitalUptakeTestCase(TestCase):
    fixtures = ['initial_types', 'test_nomis_mtp_prisons']

    def get_test_files(self):
        # NB: files contain fictitious transaction volumes
        yield from pathlib.Path(__file__).parent.glob('files/*.xls')

    def test_spreadsheet_parsing(self):
        self.assertEqual(DigitalTakeup.objects.all().count(), 0)
        for path in self.get_test_files():
            with File(path.open('rb')) as f:
                form = DigitalTakeupUploadForm(data={}, files={'excel_file': f})
                self.assertTrue(form.is_valid(), 'Excel file %s should be valid' % path)
            form.save()
        self.assertEqual(DigitalTakeup.objects.count(), 111)

        self.assertAlmostEqual(DigitalTakeup.objects.mean_digital_takeup(), 0.19, places=2)
        self.assertAlmostEqual(DigitalTakeup.objects.filter(
            start_date__range=(datetime.date(2016, 11, 2), datetime.date(2016, 11, 2))
        ).mean_digital_takeup(), 0.49, places=2)
