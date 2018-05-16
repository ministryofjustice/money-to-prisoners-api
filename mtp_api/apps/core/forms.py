import datetime

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

    def __init__(self, **kwargs):
        data = kwargs.pop('data', {})
        for field_name, field in self.base_fields.items():
            if field_name not in data:
                data[field_name] = field.initial
        super().__init__(data=data, **kwargs)


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
