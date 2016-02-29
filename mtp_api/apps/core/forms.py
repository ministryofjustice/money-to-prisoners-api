from django import forms
from django.contrib.admin import widgets
from django.utils.translation import gettext_lazy as _


class RecreateTestDataForm(forms.Form):
    scenario = forms.ChoiceField(
        choices=(
            ('cashbook', _('User testing the Cashbook service')),
            ('random', _('Random set of transactions')),
            ('delete-locations-transactions', _('Delete prisoner location and transaction data')),
        ),
    )
    number_of_transactions = forms.IntegerField(initial=100)


class AdminFilterForm(forms.Form):

    def __init__(self, *args, **kwargs):
        extra_fields = kwargs.pop('extra_fields', [])
        super().__init__(*args, **kwargs)

        for name, field in extra_fields:
            self.fields[name] = field


class SidebarDateWidget(widgets.AdminDateWidget):
    class Media:
        css = {
            'all': ('admin/css/widgets.css', 'admin/css/filter_form.css')
        }
        js = ('admin/js/calendar_overrides.js',)
