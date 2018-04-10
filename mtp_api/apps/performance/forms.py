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

from core.dashboards import DashboardChangeForm
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
                    'credits_by_post': 0,
                    'credits_by_mtp': 0,
                    'amount_by_post': 0,
                    'amount_by_mtp': 0,
                }
            if sheet.cell_value(row, 1):
                credit_type = sheet.cell_value(row, 1).upper()
                count = sheet.cell_value(row, 2)
                amount = sheet.cell_value(row, 4)
            else:
                credit_type = sheet.cell_value(row, 2).upper()
                count = sheet.cell_value(row, 3)
                amount = sheet.cell_value(row, 5)
            if credit_type not in self.credit_types:
                raise ValueError('Cannot parse credit type %s in row %d' % (credit_type, row))
            credits_key, amount_key = self.credit_types[credit_type]
            self.credits_by_prison[nomis_id][credits_key] = int(count)
            self.credits_by_prison[nomis_id][amount_key] = int(amount * 100)
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

        for nomis_id, credit_by_prison in self.credits_by_prison.items():
            DigitalTakeup.objects.update_or_create(
                defaults=credit_by_prison,
                date=self.date,
                prison_id=nomis_id,
            )

        datestr = self.date.strftime('%Y-%m-%dT00:00:00')
        job = ScheduledCommand(
            name='update_performance_platform',
            arg_string='--resources transactions-by-channel-type --timestamp %s' % datestr,
            cron_entry='*/10 * * * *',
            delete_after_next=True
        )
        job.save()


class SavingsDashboardForm(DashboardChangeForm):
    date_range = forms.ChoiceField(label=_('Date range'), required=False)
    transaction_cost_mtp = forms.DecimalField(label=_('Online cost per transaction'), min_value=0, decimal_places=2)
    transaction_cost_post = forms.DecimalField(label=_('Postal cost per transaction'), min_value=0, decimal_places=2)

    prevent_auto_reload = True

    def __init__(self, full_date_range, data, **kwargs):
        self.full_date_range = full_date_range
        earliest, latest = sorted([d.year - 1 if d.month < 4 else d.year for d in full_date_range.values()])
        choices = [
            (str(year), _('%d financial year') % year)
            for year in range(latest, earliest - 1, -1)
        ]
        choices.append(('all', _('Since the beginning')))
        data.setdefault('date_range', choices[0][0])
        data.setdefault('transaction_cost_mtp', 2.22)
        data.setdefault('transaction_cost_post', 5.73)
        super().__init__(data, **kwargs)
        self['date_range'].field.choices = choices

    def clean(self):
        super().clean()
        choice = self.cleaned_data.get('date_range')
        choice_descriptions = dict(self['date_range'].field.choices)
        self.cleaned_data['date_range_description'] = choice_descriptions[choice]
        if choice == 'all':
            self.cleaned_data['date_range'] = self.full_date_range['earliest'], self.full_date_range['latest']
        elif choice:
            financial_year = int(choice)
            start_date = datetime.date(financial_year, 4, 1)
            end_date = datetime.date(financial_year + 1, 4, 1) - datetime.timedelta(days=1)
            self.cleaned_data['date_range'] = start_date, end_date
        for key in ('transaction_cost_mtp', 'transaction_cost_post'):
            value = self.cleaned_data.get(key)
            if value:
                self.cleaned_data[key] = int(100 * value)
        return self.cleaned_data
