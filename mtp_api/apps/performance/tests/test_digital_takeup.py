import datetime
import pathlib

from django.test import TestCase
from django.core.files.base import File
from parameterized import parameterized

from performance.forms import DigitalTakeupUploadForm
from performance.models import DigitalTakeup
from prison.models import Prison


class DigitalTakeupTestCase(TestCase):
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


class DigitalTakeupUploadTestCase(TestCase):
    # NB: files contain fictitious transaction volumes
    fixtures = ['initial_types', 'test_nomis_mtp_prisons']

    def test_original_spreadsheet_parsing(self):
        self.assertEqual(DigitalTakeup.objects.all().count(), 0)
        path_to_tests = pathlib.Path(__file__).parent / 'files'
        for path in path_to_tests.glob('Money_to_Prisoner_Stats*.xls'):
            with File(path.open('rb')) as f:
                form = DigitalTakeupUploadForm(data={}, files={'excel_file': f})
                self.assertTrue(form.is_valid(),
                                msg='Excel file %s should be valid\n%s' % (path.relative_to(path_to_tests),
                                                                           form.errors.as_text()))
            form.save()
        self.assertEqual(DigitalTakeup.objects.count(), 111)

        sample_date = datetime.date(2016, 11, 2)
        self.assertAlmostEqual(DigitalTakeup.objects.mean_digital_takeup(), 0.19, places=2)
        self.assertAlmostEqual(DigitalTakeup.objects.filter(
            date=sample_date
        ).mean_digital_takeup(), 0.49, places=2)

        uptake_in_brixton = DigitalTakeup.objects.get(prison='BXI', date=sample_date)
        self.assertEqual(uptake_in_brixton.amount_by_mtp, 14240)
        self.assertEqual(uptake_in_brixton.amount_total, 34664)

    @parameterized.expand([
        # XLS, original structure, MRPR code
        ('Money_to_Prisoner_Stats - 02.11.16.xls', 4, 14240, 13 / (13 + 40)),
        # XLS, original structure, MTDS code
        ('Money_to_Prisoner_Stats - 29.01.18.xls', 107, 38716, 37 / (37 + 32)),
        # XLSX, new structure, MTDS code
        ('Money to Prisoner Stats - 07.12.2021.xlsx', 103, 62315, 39 / 39),
        # XLS, new structure, MTDS code
        ('Money to Prisoner Stats - 08.12.2021.xls', 106, 34541, 25 / 25),
    ])
    def test_new_spreadsheet_parsing(self, file_name, expected_mtp, expected_bxi_amount, expected_bxi_takeup):
        self.assertEqual(DigitalTakeup.objects.all().count(), 0)
        path = pathlib.Path(__file__).parent / 'files' / file_name
        with File(path.open('rb')) as f:
            form = DigitalTakeupUploadForm(data={}, files={'excel_file': f})
            self.assertTrue(
                form.is_valid(),
                msg=f'Excel file {file_name} should be valid\n{form.errors.as_text()}',
            )
        form.save()
        self.assertEqual(DigitalTakeup.objects.count(), expected_mtp)

        uptake_in_brixton = DigitalTakeup.objects.get(prison='BXI')
        self.assertEqual(uptake_in_brixton.amount_by_mtp, expected_bxi_amount)
        self.assertAlmostEqual(uptake_in_brixton.digital_takeup, expected_bxi_takeup, places=2)
