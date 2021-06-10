from datetime import datetime

from django import forms
from django.conf import settings
from django.conf.urls import url
from django.contrib import admin
from django.contrib.admin.utils import prepare_lookup_value
from django.utils import formats
from django.utils.translation import gettext_lazy as _

from core import getattr_path, models as core_models
from core.forms import AdminFilterForm, SidebarDateWidget


class AdminSite(admin.AdminSite):
    site_title = _('Prisoner money')
    site_header = _('Prisoner money')
    site_url = None

    def get_urls(self):
        from core.views import DashboardView, RecreateTestDataView
        from credit.views_admin import CreditReportAdminView, PrisonCreditReportAdminView
        from disbursement.views_admin import DisbursementReportAdminView, PrisonDisbursementReportAdminView
        from mtp_auth.views import LoginStatsView
        from payment.views import PaymentSearchView
        from performance.view_dashboard import PerformanceDashboardView
        from performance.views import (
            DigitalTakeupUploadView, UserSatisfactionUploadView,
            DigitalTakeupReport, PrisonDigitalTakeupView, UserSatisfactionReport,
            ZendeskReportAdminView,
        )
        from prison.views import PrisonerBalanceUploadView
        from security.views_admin import CheckReportAdminView

        return [
            # older dashboards
            url(r'^dashboard/$', DashboardView.as_view(), name='dashboard'),
            url(r'^dashboard/(?P<slug>[^/]+)/$', DashboardView.as_view(fullscreen=True), name='dashboard_fullscreen'),

            # performance dashboard and reports
            url(r'^credit/report/$', CreditReportAdminView.as_view(),
                name='credit-report'),
            url(r'^credit/prison-report/$', PrisonCreditReportAdminView.as_view(),
                name='credit-prison-report'),
            url(r'^disbursement/report/$', DisbursementReportAdminView.as_view(),
                name='disbursement-report'),
            url(r'^disbursement/prison-report/$', PrisonDisbursementReportAdminView.as_view(),
                name='disbursement-prison-report'),
            url(r'^performance/dashboard/$', PerformanceDashboardView.as_view(),
                name='performance_dashboard'),
            url(r'^performance/login-stats/$', LoginStatsView.as_view(),
                name='login-stats'),
            url(r'^performance/digitaltakeup/upload/$', DigitalTakeupUploadView.as_view(),
                name='digital_takeup_upload'),
            url(r'^performance/digitaltakeup/report/$', DigitalTakeupReport.as_view(),
                name='digital_takeup_report'),
            url(r'^performance/digitaltakeup/prisons/$', PrisonDigitalTakeupView.as_view(),
                name='digital_takeup_prisons'),
            url(r'^performance/usersatisfaction/upload/$', UserSatisfactionUploadView.as_view(),
                name='user_satisfaction_upload'),
            url(r'^performance/usersatisfaction/report/$', UserSatisfactionReport.as_view(),
                name='user_satisfaction_report'),
            url(r'^performance/zendesk-report/$', ZendeskReportAdminView.as_view(),
                name='zendesk_report'),
            url(r'^security/check/report/$', CheckReportAdminView.as_view(),
                name='check_report'),

            # additional admin views
            url(r'^payment/payment/search/$', PaymentSearchView.as_view(),
                name='payment_search'),
            url(r'^prison/prisonerbalance/upload/$', PrisonerBalanceUploadView.as_view(),
                name='prisoner_balance_upload'),

            # testing views
            url(r'^testing/recreate-data/$', RecreateTestDataView.as_view(), name='recreate_test_data'),
        ] + super().get_urls()

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}

        extra_context['show_reports'] = request.user.has_perm('transaction.view_dashboard')
        if settings.ENVIRONMENT != 'prod' and request.user.is_superuser:
            extra_context['show_recreate_test_data'] = True

        return super().index(request, extra_context)

    def has_permission(self, request):
        has_permission = super().has_permission(request)
        required_permissions = getattr_path(request, 'resolver_match.func.view_class.required_permissions', [])
        return has_permission and request.user.has_perms(required_permissions)


site = AdminSite()


def add_short_description(short_description):
    def inner(func):
        func.short_description = short_description
        return func

    return inner


class ScheduledCommandAdmin(admin.ModelAdmin):
    list_display = ('name', 'arg_string', 'cron_entry', 'next_execution',)


site.register(core_models.ScheduledCommand, ScheduledCommandAdmin)


class FileDownloadAdmin(admin.ModelAdmin):
    list_display = ('date', 'label',)


site.register(core_models.FileDownload, FileDownloadAdmin)


class FormFilter(admin.FieldListFilter):
    template = 'core/admin-form-filter.html'

    def __init__(self, field, request, params, model, model_admin, field_path):
        self.field_generic = '%s__' % field_path
        self.field_path = field_path
        self.prepare_params(params)
        super().__init__(field, request, params, model, model_admin, field_path)

    def expected_parameters(self):
        return list(next(zip(*self.get_form_fields())))

    def choices(self, cl):
        query_active = False
        fields_to_render = self.get_form_fields()

        for param, __ in fields_to_render:
            if param in cl.params:
                query_active = True
                break

        for k in cl.params:
            if not (k == self.field_path or k.startswith(self.field_generic)):
                fields_to_render.append(
                    (k, forms.CharField(widget=forms.HiddenInput()))
                )

        initial = {}
        for name, __ in fields_to_render:
            initial[name] = cl.params.get(name, '')

        form = AdminFilterForm(extra_fields=fields_to_render, initial=initial)

        return [
            {
                'selected': not query_active,
                'query_string': cl.get_query_string(
                    {}, [self.field_path, self.field_generic]
                ),
                'display': _('All')
            },
            {
                'selected': query_active,
                'form': form,
                'display': self.get_submit_label()
            },
        ]

    def get_form_fields(self):
        """
        Returns (db_field, form_field) list to be used in the filter.
        """
        raise NotImplementedError('subclasses of FormFilter must provide a get_form_fields() method')

    def get_submit_label(self):
        """
        Returns the label for the form submit button.
        """
        raise NotImplementedError('subclasses of FormFilter must provide a get_submit_label() method')

    def prepare_params(self, params):
        return params


class BaseDateFilter(FormFilter):
    def prepare_params(self, params):
        for field in self.expected_parameters():
            if field in params:
                for format in formats.get_format('DATE_INPUT_FORMATS'):
                    try:
                        params[field] = (datetime.strptime(params[field], format)
                                         .date().isoformat())
                    except (ValueError, TypeError):
                        continue


class DateRangeFilter(BaseDateFilter):
    def get_form_fields(self):
        return [
            ('%s__date__gte' % self.field_path, forms.DateField(
                widget=SidebarDateWidget(attrs={'placeholder': _('Start date')})
            )),
            ('%s__date__lte' % self.field_path, forms.DateField(
                widget=SidebarDateWidget(attrs={'placeholder': _('End date')})
            ))
        ]

    def get_submit_label(self):
        return _('Date in range')


class UtcDateRangeFilter(BaseDateFilter):
    def get_form_fields(self):
        return [
            ('%s__utcdate__gte' % self.field_path, forms.DateField(
                widget=SidebarDateWidget(attrs={'placeholder': _('Start UTC date')})
            )),
            ('%s__utcdate__lte' % self.field_path, forms.DateField(
                widget=SidebarDateWidget(attrs={'placeholder': _('End UTC date')})
            )),
        ]

    def get_submit_label(self):
        return _('UTC date in range')


class DateFilter(BaseDateFilter):
    def get_form_fields(self):
        return [
            ('%s' % self.field_path, forms.DateField(
                widget=SidebarDateWidget(attrs={'placeholder': _('Date')})
            )),
        ]

    def get_submit_label(self):
        return _('Search')


class SearchFilter(FormFilter):
    def get_form_fields(self):
        return [
            ('%s__icontains' % self.field_path, forms.CharField())
        ]

    def get_submit_label(self):
        return _('Search %(fieldname)s') % {'fieldname': self.title}


class RelatedAnyFieldListFilter(admin.RelatedFieldListFilter):
    def choices(self, cl):
        for c in super().choices(cl):
            # alter 'selected' test for empty option as default implementation
            # does not check actual value of the argument
            if c['display'] == self.empty_value_display:
                c['selected'] = (
                    self.lookup_val_isnull is not None and
                    prepare_lookup_value(
                        self.lookup_kwarg_isnull, self.lookup_val_isnull
                    )
                )

                # list 'any' option before 'none'
                yield {
                    'selected': (
                        self.lookup_val_isnull is not None and
                        not c['selected']
                    ),
                    'query_string': cl.get_query_string(
                        {self.lookup_kwarg_isnull: 'False'},
                        [self.lookup_kwarg, self.lookup_kwarg_isnull]
                    ),
                    'display': _('Any'),
                }
            yield c
