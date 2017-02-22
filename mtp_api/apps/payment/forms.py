import collections

from django import forms
from django.contrib.admin import widgets as admin_widgets
from django.core.validators import RegexValidator
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from credit.models import Credit
from prison.models import validate_prisoner_number


class PaymentSearchForm(forms.Form):
    date = forms.DateField(label=_('Payment date'), widget=admin_widgets.AdminDateWidget)
    card_number = forms.CharField(label=_('Card number'), help_text=_('Only last 4 digits are required'),
                                  validators=[RegexValidator(r'^(\d{4}\*{8}|\d{12})?\d{4}$')])
    prisoner_number = forms.CharField(label=_('Prisoner number'), required=False, validators=[validate_prisoner_number])

    error_css_class = 'errors'
    required_css_class = 'required'

    def clean_card_number(self):
        card_number = self.cleaned_data.get('card_number')
        if card_number:
            full_card_number = '%s********%s' % (card_number[:4] if len(card_number) == 16 else '****',
                                                 card_number[-4:])
            self.cleaned_data['full_card_number'] = full_card_number
            card_number = card_number[-4:]
        else:
            self.cleaned_data['full_card_number'] = ''
        return card_number

    def find(self):
        date = self.cleaned_data['date']
        card_number = self.cleaned_data['card_number']
        full_card_number = self.cleaned_data['full_card_number']
        prisoner_number = self.cleaned_data.get('prisoner_number')
        queryset = Credit.objects.filter(received_at__date=date,
                                         payment__card_number_last_digits=card_number)
        if prisoner_number:
            queryset = queryset.filter(prisoner_number=prisoner_number)

        today = now().today()
        date_format = '%02d/%02d/%d'
        today = date_format % (today.day, today.month, today.year)
        date = date_format % (date.day, date.month, date.year)

        grouped = collections.OrderedDict()
        for credit in queryset.order_by('received_at'):
            payment = credit.payment
            details = grouped.get(payment.card_expiry_date)
            if not details:
                grouped[payment.card_expiry_date] = details = []
            details.append('\t'.join([
                today, date,
                full_card_number, payment.card_expiry_date, payment.cardholder_name,
                '£%.2f' % (credit.amount / 100),
                payment.email or '', payment.ip_address or '',
                credit.prisoner_number, credit.prisoner_name, payment.recipient_name, credit.prison.short_name,
                '', str(payment.processor_id), str(credit.id),
            ]))
        return grouped
