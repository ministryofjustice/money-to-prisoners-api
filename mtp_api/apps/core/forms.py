from django import forms
from django.contrib.admin import widgets
from django.utils.translation import gettext_lazy as _


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
