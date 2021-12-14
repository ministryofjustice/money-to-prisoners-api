import collections
import datetime
import logging
import re

from django import forms
from django.conf import settings
from django.contrib.admin.widgets import AdminFileWidget
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from core.excel import ExcelWorkbook, ExcelWorksheet

logger = logging.getLogger('mtp')


class DigitalTakeupUploadForm(forms.Form):
    excel_file = forms.FileField(label=_('Excel file'), widget=AdminFileWidget)
    error_messages = {
        'cannot_read': _('Please upload a Microsoft Excel .xls or .xlsx file'),
        'invalid': _('The spreadsheet does not contain the expected structure'),
        'invalid_date': _('The report data should be for one day only'),
        'unknown_prison': _('Cannot look up prison ‘%(prison_name)s’'),
    }
    credit_types = {
        'POST': ('credits_by_post', 'amount_by_post'),
        'MTDS':  ('credits_by_mtp', 'amount_by_mtp'),
        'MRPR':  ('credits_by_mtp', 'amount_by_mtp'),  # to allow for legacy report uploading
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.date = None
        self.credits_by_prison = {}

        from prison.models import Prison

        self.re_whitespace = re.compile(r'\s+')
        self.re_prison_converters = (
            Prison.re_prefixes,  # standard prefixes
            re.compile(r'(\(.*?\))?$'),  # any parenthesised suffixes
            re.compile(r'HMP/YOI$'),  # another variation
            re.compile(r'IMMIGRATION REMOVAL CENTRE$', flags=re.IGNORECASE),  # another variation
        )

    @cached_property
    def prison_name_map(self):
        from prison.models import Prison

        prisons = list(Prison.objects.values('nomis_id', 'name'))
        prison_name_map = {
            self.re_whitespace.sub('', Prison.shorten_name(prison['name'])).upper(): prison['nomis_id']
            for prison in prisons
        }
        if len(prison_name_map) != len(prisons):
            logger.error('Generated prison name map does not have expected number of prisons')
            return {}

        return prison_name_map

    def parse_prison(self, prison_str):
        prison_str = prison_str.strip()
        for converter in self.re_prison_converters:
            prison_str = converter.sub('', prison_str)
        prison_str = self.re_whitespace.sub('', prison_str).upper()
        return self.prison_name_map[prison_str]

    @classmethod
    def find_worksheet_start(cls, sheet: ExcelWorksheet):
        # find beginning of spreadsheet as blank rows/columns has appeared over the years
        for row in range(3):
            for col in range(3):
                if (sheet.cell_value(row, col) or '').strip() == 'Parameters':
                    return row, col

    def parse_workbook(self, workbook: ExcelWorkbook):
        sheet = workbook.get_sheet(0)
        start_row, start_col = self.find_worksheet_start(sheet)

        date_formats = ['%d/%m/%Y'] + list(settings.DATE_INPUT_FORMATS)

        def parse_date(date_str, alt_date_str):
            date_str = date_str.split(':', 1)[1].strip().lstrip('0') or alt_date_str.strip().lstrip('0')
            for date_format in date_formats:
                try:
                    return datetime.datetime.strptime(date_str, date_format).date()
                except ValueError:
                    continue
            raise ValueError('Cannot parse date header %s' % date_str)

        start_date = parse_date(
            sheet.cell_value(start_row + 1, start_col),
            sheet.cell_value(start_row + 1, start_col + 1),
        )
        end_date = parse_date(
            sheet.cell_value(start_row + 2, start_col),
            sheet.cell_value(start_row + 2, start_col + 1),
        )
        if start_date != end_date:
            raise ValidationError(self.error_messages['invalid_date'], code='invalid_date')
        self.date = start_date

        row = start_row + 5
        while row < sheet.row_count:
            prison_name = sheet.cell_value(row, start_col)
            if not prison_name:
                break
            try:
                nomis_id = self.parse_prison(prison_name)
            except KeyError:
                raise ValidationError(self.error_messages['unknown_prison'], code='unknown_prison',
                                      params={'prison_name': prison_name})
            if nomis_id not in self.credits_by_prison:
                self.credits_by_prison[nomis_id] = {
                    'credits_by_post': 0,
                    'credits_by_mtp': 0,
                    'amount_by_post': 0,
                    'amount_by_mtp': 0,
                }
            if sheet.cell_value(row, start_col + 1):
                credit_type = sheet.cell_value(row, start_col + 1).upper()
                count = sheet.cell_value(row, start_col + 2)
                amount = sheet.cell_value(row, start_col + 4)
            else:
                credit_type = sheet.cell_value(row, start_col + 2).upper()
                count = sheet.cell_value(row, start_col + 3)
                amount = sheet.cell_value(row, start_col + 5)
            if credit_type == 'CHEQ':
                row += 1
                continue
            if credit_type not in self.credit_types:
                raise ValueError('Cannot parse credit type %s in row %d' % (credit_type, row))
            credits_key, amount_key = self.credit_types[credit_type]
            self.credits_by_prison[nomis_id][credits_key] = int(count)
            self.credits_by_prison[nomis_id][amount_key] = int(amount * 100)
            row += 1

    def clean_excel_file(self):
        excel_file = self.cleaned_data.get('excel_file')
        if excel_file:
            try:
                with ExcelWorkbook.open_workbook(excel_file) as workbook:
                    self.parse_workbook(workbook)
            except TypeError:
                # raised when file cannot be read
                raise ValidationError(self.error_messages['cannot_read'], code='cannot_read')
            except (ValueError, IndexError):
                # raised when file can be read but has unexpected structure/contents
                logger.warning('Cannot parse spreadsheet', exc_info=True)
                raise ValidationError(self.error_messages['invalid'], code='invalid')
        return None

    @transaction.atomic
    def save(self):
        from performance.models import DigitalTakeup

        for nomis_id, credit_by_prison in self.credits_by_prison.items():
            DigitalTakeup.objects.update_or_create(
                defaults=credit_by_prison,
                date=self.date,
                prison_id=nomis_id,
            )


class UserSatisfactionUploadForm(forms.Form):
    csv_file = forms.FileField(label=_('CSV file'), widget=AdminFileWidget)
    error_messages = {
        'cannot_read': _('Please upload a .csv file'),
        'invalid': _('The CSV file does not contain the expected structure'),
    }
    _rating_prefix = 'Rating of '

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = collections.defaultdict(lambda: collections.defaultdict(int))
        # record date range in uploaded file
        self.date_min = None
        self.date_max = None

    def parse_record(self, record):
        try:
            # filter out only aggregated daily ratings
            if record['type'] != 'aggregated-service-feedback':
                return None

            # get local date
            date = parse_datetime(record['creation date'])
            if not date:
                raise ValueError('Cannot parse creation date')
            date = timezone.make_aware(date).date()

            # get rating and count
            feedback = record['feedback']
            assert feedback.startswith(self._rating_prefix)
            feedback = feedback[len(self._rating_prefix):]
            rating, count = feedback.split(':', 1)
            rating = int(rating.strip())
            assert rating in range(1, 6)
            count = int(count.strip())
            assert count >= 0
        except (KeyError, IndexError, ValueError, AssertionError):
            raise ValidationError(self.error_messages['invalid'], 'invalid')

        return date, rating, count

    def clean_csv_file(self):
        csv_file = self.cleaned_data.get('csv_file')
        if csv_file:
            import csv
            import io

            reader = csv.DictReader(io.TextIOWrapper(csv_file))
            try:
                for record in reader:
                    parsed = self.parse_record(record)
                    if not parsed:
                        continue
                    date, rating, count = parsed
                    self.records[date][rating] = count
            except ValueError:
                raise ValidationError(self.error_messages['cannot_read'], code='cannot_read')
        return None

    @transaction.atomic
    def save(self):
        from performance.models import UserSatisfaction

        self.date_min = list(self.records)[0]
        self.date_max = self.date_min

        for date, record in self.records.items():
            UserSatisfaction.objects.update_or_create(
                defaults={
                    f'rated_{rating}': record[rating]
                    for rating in range(1, 6)
                },
                date=date,
            )

            # Keep track of records date range
            if date < self.date_min:
                self.date_min = date
            if date > self.date_max:
                self.date_max = date
