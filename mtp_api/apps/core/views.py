from io import StringIO
import logging

from django.conf import settings
from django.contrib.admin import site
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.urlresolvers import reverse_lazy
from django.forms import MediaDefiningClass
from django.http.response import Http404
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView

from core.dashboards import ExternalDashboards, TransactionReport
from core.forms import RecreateTestDataForm

logger = logging.getLogger('mtp')


class AdminViewMixin:
    """
    Mixin for custom MTP django admin views
    """
    disable_in_production = False
    superuser_required = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.request = None

    @method_decorator(site.admin_view)
    def dispatch(self, request, *args, **kwargs):
        if self.disable_in_production and settings.ENVIRONMENT == 'prod':
            raise Http404('View disabled in production')
        if self.superuser_required and not request.user.is_superuser:
            raise PermissionDenied('Superuser required')

        self.request = request
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = site.each_context(self.request)
        if hasattr(self, 'title'):
            context['title'] = self.title
        context.update(kwargs)
        return super().get_context_data(**context)


class DashboardView(AdminViewMixin, TemplateView, metaclass=MediaDefiningClass):
    """
    Django admin view which presents an overview report for MTP
    """
    title = _('Dashboard')
    template_name = 'core/dashboard/index.html'
    required_permissions = ['transaction.view_dashboard']
    reload_interval = 5 * 60

    class Media:
        css = {
            'all': ('core/css/dashboard.css',)
        }
        js = (
            'admin/js/vendor/jquery/jquery.min.js',
            'admin/js/jquery.init.js',
            'core/js/dashboard.js',
        )

    @classmethod
    def get_dashboard_modules(cls):
        dashboard_modules = [TransactionReport(), ExternalDashboards()]
        return [dashboard_module for dashboard_module in dashboard_modules if dashboard_module.enabled]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['dashboard_modules'] = self.get_dashboard_modules()
        return context


class RecreateTestDataView(AdminViewMixin, FormView):
    """
    Django admin view which calls load_test_data management command
    """
    title = _('Recreate test data')
    form_class = RecreateTestDataForm
    template_name = 'core/recreate_test_data.html'
    success_url = reverse_lazy('admin:recreate_test_data')
    disable_in_production = True
    superuser_required = True

    def form_valid(self, form):
        scenario = form.cleaned_data['scenario']

        output = StringIO()
        options = {
            'no_color': True,
            'stdout': output,
            'stderr': output,
            'number_of_transactions': form.cleaned_data['number_of_transactions']
        }

        if scenario in ('random', 'cashbook'):
            options.update({
                'protect_superusers': True,
                'protect_usernames': ['transaction-uploader'],
                'protect_transactions': False,
                'clerks_per_prison': 4,
            })
            if scenario == 'random':
                options.update({
                    'prisons': ['sample'],
                    'transactions': 'random',
                })
            elif scenario == 'cashbook':
                options.update({
                    'prisons': ['nomis'],
                    'transactions': 'nomis',
                })
            call_command('load_test_data', **options)
        elif scenario == 'delete-locations-transactions':
            options.update({
                'protect_users': 'all',
                'protect_prisons': True,
                'protect_prisoner_locations': False,
                'protect_transactions': False,
            })
            call_command('delete_all_data', **options)

        output.seek(0)
        command_output = output.read()

        logger.info('User "%(username)s" reset data for testing using "%(scenario)s" scenario' % {
            'username': self.request.user.username,
            'scenario': scenario,
        })
        logger.debug(command_output)

        return self.render_to_response(self.get_context_data(
            form=form,
            command_output=command_output,
        ))
