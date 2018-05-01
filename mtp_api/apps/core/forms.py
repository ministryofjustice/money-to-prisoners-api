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
