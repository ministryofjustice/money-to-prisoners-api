import datetime
import math

import pytz
from django import forms
from django.contrib.admin import widgets
from django.core.exceptions import ValidationError
from django.utils.timezone import now
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


class PrisonPerformaceForm(forms.Form):
    days = forms.ChoiceField(label=_('Period'), choices=(
        ('7', _('Last 7 days')),
        ('30', _('Last 30 days')),
        ('60', _('Last 60 days')),
        ('120', _('Last 120 days')),
    ), initial='30')
    order_by = forms.ChoiceField(choices=(
        ('nomis_id', _('Prison')),
        ('credit_post_count', _('Credits by post')),
        ('credit_mtp_count', _('Credits by digital service')),
        ('credit_uptake', _('Digital take-up')),
        ('disbursement_count', _('Disbursements')),
    ), initial='nomis_id')
    desc = forms.ChoiceField(choices=(
        ('', _('Ascending')),
        ('1', _('Descending')),
    ), required=False)

    def __init__(self, **kwargs):
        data = kwargs.pop('data', {})
        for field_name, field in self.base_fields.items():
            if field_name not in data:
                data[field_name] = field.initial
        super().__init__(data=data, **kwargs)


class DigitalTakeupReportForm(forms.Form):
    period = forms.ChoiceField(label=_('Report type'), choices=(
        ('monthly', _('Monthly')),
        ('quarterly', _('Quarterly')),
        ('financial', _('Financial years')),
    ), initial='monthly')
    show_reported = forms.ChoiceField(label=_('Reported data'), choices=(
        ('hide', _('Hide')),
        ('show', _('Show')),
    ), initial='hide')
    show_predictions = forms.ChoiceField(label=_('Predictions'), choices=(
        ('hide', _('Hide')),
        ('show', _('Show')),
    ), initial='hide')
    postal_cost = forms.IntegerField(label=_('Cost per postal transaction'), min_value=0, initial=573)
    digital_cost = forms.IntegerField(label=_('Cost per digital transaction'), min_value=0, initial=222)

    def __init__(self, **kwargs):
        data = kwargs.pop('data', {})
        for field_name, field in self.base_fields.items():
            if field_name not in data:
                data[field_name] = field.initial
        super().__init__(data=data, **kwargs)

    @property
    def current_period(self):
        first_of_month = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
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
            today = now()
            if 'iat' in self.decoded_token and self.decoded_token['iat'] > today:
                raise ValidationError(_('Token is not yet valid'), 'premature')
            if 'exp' in self.decoded_token and self.decoded_token['exp'] < today:
                raise ValidationError(_('Token has already expired'), 'expired')
        except (ValueError, jwt.DecodeError):
            raise ValidationError(_('Invalid client token'), 'invalid')
        return token
