from io import StringIO
import json
import logging
from urllib.parse import unquote as url_unquote

from django.conf import settings
from django.contrib.admin import site
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.urlresolvers import reverse_lazy
from django.forms import MediaDefiningClass
from django.http.response import Http404
from django.utils.decorators import method_decorator
from django.utils.module_loading import autodiscover_modules
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView

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
    cookie_name = 'mtp-dashboard'
    reload_interval = 5 * 60
    _registry = []

    class Media:
        css = {
            'all': ('core/css/dashboard.css',)
        }
        js = (
            'core/js/js.cookie-2.1.1.min.js',
            'admin/js/vendor/jquery/jquery.min.js',
            'admin/js/jquery.init.js',
            'core/js/dashboard.js',
        )

    @classmethod
    def register_dashboard(cls, dashboard_class):
        cls._registry.append(dashboard_class)
        return dashboard_class

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cookie_data = {}

    def dispatch(self, request, *args, **kwargs):
        try:
            self.cookie_data = json.loads(url_unquote(request.COOKIES.get(self.cookie_name, '')))
        except (TypeError, ValueError):
            pass
        return super().dispatch(request, *args, **kwargs)

    def get_dashboards(self):
        cls = self.__class__
        if not cls._registry:
            autodiscover_modules('dashboards', register_to=cls)

        dashboards = map(lambda d: d(dashboard_view=self),
                         cls._registry)
        return sorted((dashboard for dashboard in dashboards if dashboard.enabled),
                      key=lambda dashboard: dashboard.priority, reverse=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['dashboard_modules'] = self.get_dashboards()
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
