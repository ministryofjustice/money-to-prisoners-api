import datetime
import logging
import re

from django import forms
from django.conf import settings
from django.contrib.admin.widgets import AdminFileWidget
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from core.models import ScheduledCommand

logger = logging.getLogger('mtp')


class DigitalTakeupUploadForm(forms.Form):
    excel_file = forms.FileField(label=_('Excel file'), widget=AdminFileWidget)
    error_messages = {
        'cannot_read': _('Please upload a Microsoft Excel 97-2003 .xls file'),
        'invalid': _('The spreadsheet does not contain the expected structure'),
        'invalid_date': _('The report data should be for one day only'),
        'unknown_prison': _('Cannot look up prison ‘%(prison_name)s’'),
    }
    credit_type_mtp = 'MTDS'
    credit_type_post = 'POST'

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

    def parse_excel_sheet(self, sheet):
        date_formats = ['%d/%m/%Y'] + list(settings.DATE_INPUT_FORMATS)
        data_start_row = 6

        def parse_date(date_str, alt_date_str):
            date_str = date_str.split(':', 1)[1].strip().lstrip('0') or alt_date_str.strip().lstrip('0')
            for date_format in date_formats:
                try:
                    return datetime.datetime.strptime(date_str, date_format).date()
                except ValueError:
                    continue
            raise ValueError('Cannot parse date header %s' % date_str)

        start_date = parse_date(sheet.cell_value(2, 0), sheet.cell_value(2, 1))
        end_date = parse_date(sheet.cell_value(3, 0), sheet.cell_value(3, 1))
        if start_date != end_date:
            raise ValidationError(self.error_messages['invalid_date'], code='invalid_date')
        self.date = start_date

        row = data_start_row
        while row < sheet.nrows:
            prison_name = sheet.cell_value(row, 0)
            if not prison_name:
                break
            try:
                nomis_id = self.parse_prison(prison_name)
            except KeyError:
                raise ValidationError(self.error_messages['unknown_prison'], code='unknown_prison',
                                      params={'prison_name': prison_name})
            if nomis_id not in self.credits_by_prison:
                self.credits_by_prison[nomis_id] = {
                    self.credit_type_mtp: 0,
                    self.credit_type_post: 0,
                }
            if sheet.cell_value(row, 1):
                credit_type = sheet.cell_value(row, 1).upper()
                count = sheet.cell_value(row, 2)
            else:
                credit_type = sheet.cell_value(row, 2).upper()
                count = sheet.cell_value(row, 3)
            if credit_type not in self.credits_by_prison[nomis_id]:
                raise ValueError('Cannot parse credit type %s in row %d' % (credit_type, row))
            self.credits_by_prison[nomis_id][credit_type] = int(count)
            row += 1

    def clean_excel_file(self):
        excel_file = self.cleaned_data.get('excel_file')
        if excel_file:
            from xlrd import open_workbook, XLRDError
            from xlrd.compdoc import CompDocError

            try:
                with open_workbook(filename=excel_file.name, file_contents=excel_file.read(),
                                   on_demand=True) as work_book:
                    sheet = work_book.get_sheet(0)
                    self.parse_excel_sheet(sheet)
            except (IndexError, CompDocError, XLRDError):
                raise ValidationError(self.error_messages['cannot_read'], code='cannot_read')
            except ValueError:
                logger.warning('Cannot parse spreadsheet', exc_info=True)
                raise ValidationError(self.error_messages['invalid'], code='invalid')
        return None

    @transaction.atomic
    def save(self):
        from performance.models import DigitalTakeup

        takeup = [
            DigitalTakeup.objects.update_or_create(
                defaults=dict(
                    credits_by_post=credit_by_prison[DigitalTakeupUploadForm.credit_type_post],
                    credits_by_mtp=credit_by_prison[DigitalTakeupUploadForm.credit_type_mtp],
                ),
                date=self.date,
                prison_id=nomis_id,
            )[0]
            for nomis_id, credit_by_prison in self.credits_by_prison.items()
        ]

        datestr = self.date.strftime('%Y-%m-%dT00:00:00')
        job = ScheduledCommand(
            name='update_performance_platform',
            arg_string='--resources transactions-by-channel-type --timestamp %s' % datestr,
            cron_entry='*/10 * * * *',
            delete_after_next=True
        )
        job.save()

        return takeup
