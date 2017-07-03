from django import forms
from django.utils.translation import gettext_lazy as _


class LoadOffendersForm(forms.Form):
    modified_only = forms.BooleanField(label=_('Only load updated offender locations'), required=False)
