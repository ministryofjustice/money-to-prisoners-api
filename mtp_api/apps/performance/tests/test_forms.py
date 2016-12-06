import datetime
import pathlib

from django.test import TestCase
from django.core.files.base import File

from performance.forms import DigitalTakeupUploadForm
from performance.models import DigitalTakeup


class DigitalUptakeTestCase(TestCase):
    fixtures = ['initial_types', 'test_nomis_mtp_prisons']

    def test_spreadsheet_parsing(self):
        # NB: files contain fictitious transaction volumes
        self.assertEqual(DigitalTakeup.objects.all().count(), 0)
        path_to_tests = pathlib.Path(__file__).parent / 'files'
        for path in path_to_tests.glob('*.xls'):
            with File(path.open('rb')) as f:
                form = DigitalTakeupUploadForm(data={}, files={'excel_file': f})
                self.assertTrue(form.is_valid(),
                                msg='Excel file %s should be valid\n%s' % (path.relative_to(path_to_tests),
                                                                           form.errors.as_text()))
            form.save()
        self.assertEqual(DigitalTakeup.objects.count(), 111)

        self.assertAlmostEqual(DigitalTakeup.objects.mean_digital_takeup(), 0.19, places=2)
        self.assertAlmostEqual(DigitalTakeup.objects.filter(
            date=datetime.date(2016, 11, 2)
        ).mean_digital_takeup(), 0.49, places=2)