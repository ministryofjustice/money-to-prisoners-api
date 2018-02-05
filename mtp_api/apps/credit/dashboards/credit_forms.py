import datetime
import types

from django import forms
from django.contrib.admin import widgets as admin_widgets
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateformat import format as format_date
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from core.dashboards import DashboardChangeForm
from credit.models import Credit
from prison.models import Prison
from transaction.models import Transaction


class DateField(forms.DateField):
    widget = admin_widgets.AdminDateWidget

    def get_bound_field(self, form, field_name):
        bound_field = super().get_bound_field(form, field_name)
        super_css_classes = bound_field.css_classes

        def css_classes(_, extra_classes=None):
            classes = super_css_classes(extra_classes=extra_classes)
            return (classes + ' row_%s' % field_name).strip()

        bound_field.css_classes = types.MethodType(css_classes, bound_field)
        return bound_field


class SimpleDurationField(forms.FloatField):
    default_error_messages = {
        'invalid': _('Enter number of days'),
    }

    def prepare_value(self, value):
        if isinstance(value, datetime.timedelta):
            return value.days + value.seconds / 86400
        return super().prepare_value(value)

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, datetime.timedelta):
            return value
        try:
            return datetime.timedelta(days=float(value))
        except ValueError:
            raise ValidationError(self.error_messages['invalid'], code='invalid')


class CreditForm(DashboardChangeForm):
    date_range = forms.ChoiceField(
        label=_('Date range'),
        choices=[
            ('today', _('Today')),
            ('yesterday', _('Yesterday')),
            ('this_week', _('This week')),
            ('last_week', _('Last week')),
            ('four_weeks', _('Last 4 weeks')),
            ('this_month', _('This month')),
            ('last_month', _('Last month')),
            # ('all', _('Since the beginning')),
            ('custom', _('Specify a range…')),
        ],
        initial='this_week',
        required=False,
    )
    start_date = DateField(label=_('From date'), required=False)
    end_date = DateField(label=_('To date'), required=False)
    prison = forms.ModelChoiceField(
        queryset=Prison.objects.all(),
        label=_('Prison'),
        empty_label=_('All prisons'),
        required=False,
    )

    prevent_auto_reload = True
    error_messages = {
        'date_order': _('End date must be after start date'),
        'big_range': _('Choose a smaller date range'),
    }

    def clean_end_date(self):
        start_date = self.cleaned_data.get('start_date')
        end_date = self.cleaned_data.get('end_date')
        if start_date and end_date and self.cleaned_data.get('date_range') == 'custom':
            if end_date < start_date:
                raise forms.ValidationError(self.error_messages['date_order'], code='date_order')
            if end_date - start_date > datetime.timedelta(days=60):
                raise forms.ValidationError(self.error_messages['big_range'], code='big_range')
        return end_date

    @cached_property
    def today(self):
        return timezone.localtime(timezone.now()).date()

    @cached_property
    def yesterday(self):
        return self.today - datetime.timedelta(days=1)

    @cached_property
    def earliest(self):
        try:
            return timezone.localtime(Credit.objects.earliest().received_at).date()
        except Credit.DoesNotExist:
            pass

    @cached_property
    def latest(self):
        try:
            return timezone.localtime(Credit.objects.latest().received_at).date()
        except Credit.DoesNotExist:
            pass

    @cached_property
    def this_week(self):
        monday = self.today - datetime.timedelta(days=self.today.weekday())
        return monday, monday + datetime.timedelta(days=6)

    @cached_property
    def last_week(self):
        monday = self.today - datetime.timedelta(days=self.today.weekday() + 7)
        return monday, monday + datetime.timedelta(days=6)

    @cached_property
    def four_weeks(self):
        return self.today - datetime.timedelta(days=4 * 7), self.today

    @cached_property
    def this_month(self):
        return self.today.replace(day=1), self.today

    @cached_property
    def last_month(self):
        last_day = self.today.replace(day=1) - datetime.timedelta(days=1)
        return last_day.replace(day=1), last_day

    def get_date_range(self):
        date_range = self.cleaned_data['date_range'] or self['date_range'].field.initial
        if date_range == 'custom' and (self.cleaned_data.get('start_date') or self.cleaned_data.get('end_date')):
            received_at_start = self.cleaned_data.get('start_date', self.earliest)
            received_at_end = self.cleaned_data.get('end_date', self.latest)
            if received_at_start == received_at_end:
                short_title = format_date(received_at_start, 'j M Y')
            else:
                if received_at_start.replace(day=1) == received_at_end.replace(day=1):
                    from_date_format = 'j'
                elif received_at_start.replace(month=1, day=1) == received_at_end.replace(month=1, day=1):
                    from_date_format = 'j M'
                else:
                    from_date_format = 'j M Y'
                short_title = _('%(from)s to %(to)s') % {
                    'from': format_date(received_at_start, from_date_format),
                    'to': format_date(received_at_end, 'j M Y')
                }
            return {
                'range': (received_at_start, received_at_end),
                'short_title': short_title,
                'title': short_title,
            }
        elif date_range in ('this_week', 'last_week', 'four_weeks', 'this_month', 'last_month'):
            received_at_start, received_at_end = getattr(self, date_range)
            short_title = dict(self['date_range'].field.choices)[date_range]
            if date_range in ('this_month', 'last_month'):
                month = format_date(received_at_start, 'N Y')
                title = '%(title)s, %(month)s' % {
                    'title': short_title,
                    'month': month,
                }
                short_title = month
            else:
                title = '%(title)s, commencing %(day)s' % {
                    'title': short_title,
                    'day': format_date(received_at_start, 'j N'),
                }
            return {
                'range': (received_at_start, received_at_end),
                'short_title': short_title,
                'title': title,
            }
        elif date_range in ('today', 'yesterday'):
            received_at = getattr(self, date_range)
            short_title = dict(self['date_range'].field.choices)[date_range]
            return {
                'range': (received_at,),
                'short_title': short_title,
                'title': '%(title)s, %(day)s' % {
                    'title': short_title,
                    'day': format_date(received_at, 'j N'),
                },
            }

        # all time
        return {
            'range': (),
            'short_title': _('Since the beginning'),
            'title': _('Since the beginning'),
        }

    def get_prison(self):
        if self.is_valid():
            return self.cleaned_data['prison']

    def get_report_parameters(self):
        credit_queryset = Credit.objects.all()
        transaction_queryset = Transaction.objects.all()

        prison = self.get_prison()
        if prison:
            credit_queryset = credit_queryset.filter(prison=prison)
            transaction_queryset = transaction_queryset.filter(credit__prison=prison)

        chart_credit_queryset = credit_queryset.filter()

        date_range = self.get_date_range()
        if len(date_range['range']) == 2:
            title = date_range['title']
            received_at_start, received_at_end = date_range['range']
            date_filters = {
                'received_at__date__gte': received_at_start,
                'received_at__date__lte': received_at_end,
            }
            admin_filter_string = 'received_at__date__gte=%s&' \
                                  'received_at__date__lte=%s' % (received_at_start.isoformat(),
                                                                 received_at_end.isoformat())
            chart_title = date_range['short_title']
            chart_start_date = received_at_start
            chart_end_date = received_at_end
        elif len(date_range['range']) == 1:
            title = date_range['title']
            received_at, = date_range['range']
            date_filters = {
                'received_at__date': received_at
            }
            admin_filter_string = 'received_at__day=%d&' \
                                  'received_at__month=%d&' \
                                  'received_at__year=%d' % (received_at.day,
                                                            received_at.month,
                                                            received_at.year)
            chart_title = _('Last 4 weeks')
            chart_start_date = self.four_weeks[0]
            chart_end_date = self.four_weeks[1]
        else:
            title = date_range['title']
            date_filters = {}
            admin_filter_string = ''
            chart_title = date_range['short_title']
            chart_start_date = None
            chart_end_date = None

        extra_titles = []
        if prison:
            extra_titles.append(_('only for %(prison)s') % {'prison': prison})
        if extra_titles:
            title += ' (%s)' % ', '.join(extra_titles)

        credit_queryset = credit_queryset.filter(**date_filters)
        transaction_queryset = transaction_queryset.filter(**date_filters)
        if chart_start_date:
            chart_credit_queryset = chart_credit_queryset.filter(received_at__date__gte=chart_start_date)
        if chart_end_date:
            chart_credit_queryset = chart_credit_queryset.filter(received_at__date__lte=chart_end_date)

        return {
            'title': title,
            'credit_queryset': credit_queryset,
            'transaction_queryset': transaction_queryset,
            'admin_filter_string': admin_filter_string,
            'chart_title': chart_title,
            'chart_credit_queryset': chart_credit_queryset,
            'chart_start_date': chart_start_date,
            'chart_end_date': chart_end_date,
        }
