import collections
import datetime
import math
from urllib.parse import urlencode

import pytz
from django import forms
from django.contrib.admin import widgets
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
import jwt


class RecreateTestDataForm(forms.Form):
    scenario = forms.ChoiceField(
        choices=(
            ('cashbook', _('User testing the Cashbook service')),
            ('nomis-api-dev', _('NOMIS API dev env data')),
            ('random', _('Random set of credits')),
            ('delete-locations-credits', _('Delete prisoner location and credit data')),
        ),
    )
    number_of_transactions = forms.IntegerField(initial=20)
    number_of_payments = forms.IntegerField(initial=200)
    number_of_disbursements = forms.IntegerField(initial=50)
    number_of_prisoners = forms.IntegerField(initial=50)
    digital_takeup = forms.BooleanField(initial=True, required=False)
    days_of_history = forms.IntegerField(initial=7)


class AdminFilterForm(forms.Form):
    def __init__(self, *args, **kwargs):
        extra_fields = kwargs.pop('extra_fields', [])
        super().__init__(*args, **kwargs)

        for name, field in extra_fields:
            self.fields[name] = field


class SidebarDateWidget(widgets.AdminDateWidget):
    class Media:
        css = {
            'all': ('admin/css/widgets.css', 'stylesheets/filter-form.css')
        }
        js = ('javascripts/vendor/calendar-overrides.js',)


class AdminReportForm(forms.Form):
    def __init__(self, **kwargs):
        data = kwargs.pop('data', {})
        for field_name, field in self.base_fields.items():
            if field_name not in data:
                data[field_name] = field.initial
        super().__init__(data=data, **kwargs)

        if 'ordering' in self.fields:
            ordering_field = self.fields['ordering']
            reversed_choices = [
                (f'-{value}', label)
                for value, label in ordering_field.choices
            ]
            ordering_field.choices.extend(reversed_choices)

    @cached_property
    def query_string_without_ordering(self):
        query = (
            (field.name, self.cleaned_data.get(field.name))
            for field in self
            if field.name not in {'ordering'}
        )
        query = filter(lambda q: q[1] not in (None, '', []), query)
        query = dict(query)
        return urlencode(query, doseq=True)

    def get_ordering(self):
        if 'ordering' not in self.fields:
            return None, None
        ordering = self.cleaned_data['ordering']
        if ordering.startswith('-'):
            return ordering[1:], True
        return ordering, False


class BasePrisonAdminReportForm(AdminReportForm):
    period = forms.ChoiceField(label=_('Period'), choices=(
        ('7', _('Last 7 days')),
        ('30', _('Last 30 days')),
        ('this_month', _('This month')),
        ('last_month', _('Last month')),
        ('this_quarter', _('This quarter')),
        ('last_quarter', _('Last quarter')),
        ('this_fin_year', _('This financial year')),
        ('last_fin_year', _('Last financial year')),
    ), initial='30')

    @property
    def period_date_range(self):
        period = self.cleaned_data['period']
        today = timezone.localtime()

        try:
            days = int(period)
        except ValueError:
            pass
        else:
            since_date = today.date() - datetime.timedelta(days=days)
            return since_date, None

        first_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if period == 'this_month':
            return first_of_month.date(), None
        if period == 'last_month':
            last_month = first_of_month.month - 1
            if last_month < 1:
                first_of_last_month = first_of_month.replace(
                    year=first_of_month.year - 1,
                    month=12,
                )
            else:
                first_of_last_month = first_of_month.replace(month=last_month)
            return first_of_last_month.date(), first_of_month.date()

        first_of_quarter = first_of_month.replace(month=math.ceil(first_of_month.month / 3) * 3 - 2)
        if period == 'this_quarter':
            return first_of_quarter.date(), None
        if period == 'last_quarter':
            last_quarter_month = first_of_quarter.month - 4
            if last_quarter_month < 1:
                first_of_last_quarter = first_of_quarter.replace(
                    year=first_of_month.year - 1,
                    month=10,
                )
            else:
                first_of_last_quarter = first_of_quarter.replace(month=last_quarter_month)
            return first_of_last_quarter.date(), first_of_quarter.date()

        if first_of_quarter.month == 4:
            first_of_fin_year = first_of_quarter
        else:
            first_of_fin_year = first_of_quarter.replace(year=first_of_quarter.year - 1, month=4)
        if period == 'this_fin_year':
            return first_of_fin_year.date(), None
        if period == 'last_fin_year':
            first_of_last_fin_year = first_of_fin_year.replace(year=first_of_fin_year.year - 1)
            return first_of_last_fin_year.date(), first_of_fin_year.date()

        raise NotImplementedError


class PrisonDigitalTakeupForm(BasePrisonAdminReportForm):
    ordering = forms.ChoiceField(choices=(
        ('nomis_id', _('Prison')),
        ('credits_by_post', _('Credits by post')),
        ('credits_by_mtp', _('Credits by digital service')),
        ('digital_takeup', _('Digital take-up')),
    ), initial='nomis_id')


class BasePeriodAdminReportForm(AdminReportForm):
    period = forms.ChoiceField(label=_('Report type'), choices=(
        ('monthly', _('Monthly')),
        ('quarterly', _('Quarterly')),
        ('financial', _('Financial years')),
    ), initial='monthly')

    @property
    def current_period(self):
        first_of_month = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period = self.cleaned_data['period']
        if period == 'quarterly':
            return first_of_month.replace(month=math.ceil(first_of_month.month / 3) * 3 - 2)
        elif period == 'financial':
            if first_of_month.month < 4:
                return first_of_month.replace(year=first_of_month.year - 1, month=4)
            else:
                return first_of_month.replace(month=4)
        return first_of_month

    @property
    def period_formatter(self):
        period = self.cleaned_data['period']
        if period == 'quarterly':
            return lambda d: 'Q%d %d' % (math.ceil(d.month / 3), d.year)
        elif period == 'financial':
            def format_date(d):
                if d.month < 4:
                    year = d.year - 1
                else:
                    year = d.year
                return '%(april)s %(year1)d to %(april)s %(year2)d' % {
                    'april': _('April'),
                    'year1': year,
                    'year2': year + 1,
                }

            return format_date
        return lambda d: d.strftime('%b %Y')

    def group_months_into_periods(self, monthly_rows):
        if self.cleaned_data['period'] == 'quarterly':
            yield from self.group_months_into_quarters(monthly_rows)
        elif self.cleaned_data['period'] == 'financial':
            yield from self.group_months_into_financial_years(monthly_rows)
        else:
            yield from monthly_rows

    def group_months_into_quarters(self, monthly_rows):
        quarter_end_months = {3, 6, 9, 12}
        collected = collections.defaultdict(int)
        for row in monthly_rows:
            row_date = row.pop('date')
            if 'date' not in collected:
                collected['date'] = row_date
            for key, value in row.items():
                if value is None:
                    collected[key] = None
                else:
                    collected[key] += value
            if row_date.month in quarter_end_months:
                yield collected
                collected = collections.defaultdict(int)
        if 'date' in collected:
            yield collected

    def group_months_into_financial_years(self, monthly_rows):
        collected = collections.defaultdict(int)
        for row in monthly_rows:
            row_date = row.pop('date')
            if 'date' not in collected:
                collected['date'] = row_date
            for key, value in row.items():
                if value is None:
                    collected[key] = None
                else:
                    collected[key] += value
            if row_date.month == 3:
                yield collected
                collected = collections.defaultdict(int)
        if 'date' in collected:
            yield collected


class DigitalTakeupReportForm(BasePeriodAdminReportForm):
    private_estate = forms.ChoiceField(label=_('Private estate'), choices=(
        ('exclude', _('Exclude')),
        ('include', _('Include')),
    ), initial='exclude')
    show_reported = forms.ChoiceField(label=_('Data from NOMIS'), choices=(
        ('hide', _('Hide')),
        ('show', _('Show')),
    ), initial='hide')
    show_savings = forms.ChoiceField(label=_('Gross savings enabled'), choices=(
        ('hide', _('Hide')),
        ('show', _('Show')),
    ), initial='hide')
    show_predictions = forms.ChoiceField(label=_('Predictions'), choices=(
        ('hide', _('Hide')),
        ('show', _('Show')),
    ), initial='hide')
    postal_cost = forms.IntegerField(label=_('Cost per postal transaction'), min_value=0, initial=573)
    digital_cost = forms.IntegerField(label=_('Cost per digital transaction'), min_value=0, initial=222)

    @property
    def prediction_scale(self):
        period = self.cleaned_data['period']
        if period == 'quarterly':
            return 3
        if period == 'financial':
            return 12
        return 1

    def get_periods_to_predict(self, date):
        period = self.cleaned_data['period']
        if period == 'quarterly':
            # this quarter and next 2
            for _ in range(1, 4):  # noqa: F402
                month = date.month + 3
                if month > 12:
                    date = date.replace(year=date.year + 1)
                    month = 1
                date = date.replace(month=month)
                yield date
        elif period == 'financial':
            # this financial year and next
            yield date.replace(year=date.year + 1)
            yield date.replace(year=date.year + 2)
        else:
            # this month and next 11
            for _ in range(1, 13):  # noqa: F402
                month = date.month + 1
                if month > 12:
                    date = date.replace(year=date.year + 1)
                    month = 1
                date = date.replace(month=month)
                yield date


# TODO: Remove once all apps move to NOMIS Elite2
class UpdateNOMISTokenForm(forms.Form):
    token = forms.FileField(label=_('Client token file'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token_data = None
        self.decoded_token = None

    @classmethod
    def decode_token(cls, token):
        token = jwt.decode(token, verify=False)
        for date_key in ('iat', 'exp'):
            if date_key in token:
                token[date_key] = datetime.datetime.utcfromtimestamp(token[date_key]).replace(tzinfo=pytz.utc)
        return token

    def clean_token(self):
        token = self.cleaned_data.get('token')
        try:
            self.token_data = token.read().strip()
            self.decoded_token = self.decode_token(self.token_data)
            today = timezone.now()
            if 'iat' in self.decoded_token and self.decoded_token['iat'] > today:
                raise ValidationError(_('Token is not yet valid'), 'premature')
            if 'exp' in self.decoded_token and self.decoded_token['exp'] < today:
                raise ValidationError(_('Token has already expired'), 'expired')
        except (ValueError, jwt.DecodeError):
            raise ValidationError(_('Invalid client token'), 'invalid')
        return token
