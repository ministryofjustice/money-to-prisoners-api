from django import forms
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _


class RecreateTestDataForm(forms.Form):
    protect_transactions = forms.BooleanField(
        required=False,
        initial=False,
        help_text=_('Prevents existing transactions from being deleted'),
    )
    generate_transactions = forms.ChoiceField(
        required=True,
        initial='none',
        choices=[[item, capfirst(item)] for item in ['none', 'random']],
        help_text=_('Create new transactions using this method'),
    )
