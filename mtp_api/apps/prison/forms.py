import csv
import decimal
import io

from django import forms
from django.contrib.admin.widgets import AdminFileWidget
from django.db import transaction
from django.forms.models import ModelChoiceField
from django.utils.translation import gettext_lazy as _

from prison.models import Prison, PrisonerBalance, validate_prisoner_number


class PrisonerBalanceUploadForm(forms.Form):
    csv_file = forms.FileField(label=_('Prisoner balances file'), allow_empty_file=True, widget=AdminFileWidget)
    prison = ModelChoiceField(queryset=Prison.objects.filter(use_nomis_for_balances=False))

    def clean_csv_file(self):
        csv_file = self.cleaned_data.get('csv_file')
        if csv_file:
            try:
                return self.parse_balances(csv_file)
            except Exception as e:
                self.add_error('csv_file', f'Could not parse file: {e}')
        return None

    @classmethod
    def parse_balances(cls, csv_file):
        csv_contents = csv_file.read().decode()
        csv_contents = io.StringIO(csv_contents)
        csv_reader = csv.DictReader(csv_contents)
        balances = []
        for line in csv_reader:
            prisoner_number = line['prisonnumber'].strip().upper()
            # check that prisoner number follows expected pattern (else indicates malformed file)
            validate_prisoner_number(prisoner_number)
            amount = line['totalamount']
            amount_pence = decimal.Decimal(amount.strip()) * 100
            # check that amount_pence is not negative (assumed impossible)
            # and has no decimal places (indicates malformed file)
            numerator, denomiator = amount_pence.as_integer_ratio()
            if numerator <= 0:
                raise ValueError('Negative balance', {'amount': amount})
            if denomiator != 1:
                raise ValueError('Cannot turn amount into pence', {'amount': amount})
            balances.append({
                'prisoner_number': prisoner_number,
                'amount': int(amount_pence),
            })
        return balances

    @transaction.atomic
    def save(self):
        prison = self.cleaned_data['prison']
        balances = self.cleaned_data['csv_file']
        balances = [
            PrisonerBalance(
                prison=prison,
                prisoner_number=balance['prisoner_number'],
                amount=balance['amount'],
            )
            for balance in balances
        ]
        # delete all balances at this prison (because small balances will not be provided in spreadsheet)
        delete_result = PrisonerBalance.objects.filter(prison=prison).delete()
        deleted = delete_result[0]
        # delete all existing balances for given prisoners (in case there are transfers)
        delete_result = PrisonerBalance.objects.filter(
            prisoner_number__in=set(balance.prisoner_number for balance in balances),
        ).delete()
        deleted += delete_result[0]
        # save new balances
        create_result = PrisonerBalance.objects.bulk_create(balances)
        created = len(create_result)
        return {
            'deleted': deleted,
            'created': created,
        }
