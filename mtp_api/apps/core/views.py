from io import StringIO
import json
import logging
from urllib.parse import unquote as url_unquote

from django.conf import settings
from django.contrib import messages
from django.contrib.admin import site
from django.contrib.admin.models import LogEntry, CHANGE as CHANGE_LOG_ENTRY
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.forms import MediaDefiningClass
from django.http.response import Http404, HttpResponse
from django.urls import reverse_lazy
from django.utils.dateparse import parse_date
from django.utils.decorators import method_decorator
from django.utils.module_loading import autodiscover_modules
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import FormView, TemplateView

from mtp_auth.permissions import (
    get_client_permissions_class,
    BankAdminClientIDPermissions, CASHBOOK_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID,
)
from rest_framework import generics, mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.forms import RecreateTestDataForm, UpdateNOMISTokenForm
from core.models import FileDownload, Token
from core.permissions import ActionsBasedPermissions, TokenPermissions
from core.serializers import FileDownloadSerializer, TokenSerializer

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
    reload_interval = 600  # 10min
    fullscreen = False
    autodiscovered = False
    _registry = []

    class Media:
        css = {
            'all': ('stylesheets/dashboard.css',)
        }
        js = (
            'javascripts/vendor/js.cookie-2.1.3.min.js',
            'admin/js/vendor/jquery/jquery.min.js',
            'admin/js/jquery.init.js',
            'javascripts/dashboard.js',
        )

    @classmethod
    def register_dashboard(cls, dashboard_class):
        cls._registry.append(dashboard_class)
        return dashboard_class

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cookie_data = {}
        self.slug = None

    def dispatch(self, request, *args, slug=None, **kwargs):
        self.slug = slug
        try:
            self.cookie_data = json.loads(url_unquote(request.COOKIES.get(self.cookie_name, '')))
        except (TypeError, ValueError):
            pass
        return super().dispatch(request, *args, **kwargs)

    def get_dashboards(self):
        cls = self.__class__
        if not cls.autodiscovered:
            cls.autodiscovered = True
            autodiscover_modules('dashboards', register_to=cls)

        dashboards = cls._registry
        if self.slug:
            dashboards = filter(lambda d: d.slug == self.slug, dashboards)
        dashboards = filter(lambda d: d.enabled, map(lambda d: d(view=self), dashboards))
        dashboards = sorted(dashboards, key=lambda dashboard: dashboard.priority, reverse=True)
        if not dashboards:
            raise Http404('No enabled dashboards')
        return dashboards

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dashboard_modules = self.get_dashboards()
        combined_media = self.media
        for dashboard_module in dashboard_modules:
            combined_media += dashboard_module.media
            if hasattr(dashboard_module, 'form'):
                combined_media += dashboard_module.form.media
        context.update({
            'dashboard_modules': dashboard_modules,
            'combined_media': combined_media,
            'fullscreen': self.fullscreen,
        })
        return context


class RecreateTestDataView(AdminViewMixin, FormView):
    """
    Django admin view which calls load_test_data management command
    """
    title = _('Recreate test data')
    form_class = RecreateTestDataForm
    template_name = 'core/recreate-test-data.html'
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
            'number_of_transactions': form.cleaned_data['number_of_transactions'],
            'number_of_payments': form.cleaned_data['number_of_payments'],
            'number_of_disbursements': form.cleaned_data['number_of_disbursements'],
            'number_of_prisoners': form.cleaned_data['number_of_prisoners'],
            'digital_takeup': form.cleaned_data['digital_takeup'],
            'days_of_history': form.cleaned_data['days_of_history'],
        }

        if scenario in ('random', 'cashbook', 'training', 'nomis-api-dev'):
            options.update({
                'protect_superusers': True,
                'protect_usernames': ['transaction-uploader'],
                'protect_credits': False,
                'clerks_per_prison': 4,
            })
            if scenario == 'random':
                options.update({
                    'prisons': ['sample'],
                    'prisoners': ['sample'],
                    'credits': 'random',
                })
            elif scenario == 'cashbook':
                options.update({
                    'prisons': ['nomis'],
                    'prisoners': ['sample'],
                    'credits': 'nomis',
                })
            elif scenario == 'nomis-api-dev':
                options.update({
                    'prisons': ['nomis-api-dev'],
                    'prisoners': ['nomis-api-dev'],
                    'credits': 'nomis',
                })
            call_command('load_test_data', **options)
        elif scenario == 'delete-locations-credits':
            options.update({
                'protect_users': 'all',
                'protect_prisons': True,
                'protect_prisoner_locations': False,
                'protect_credits': False,
            })
            call_command('delete_all_data', **options)

        output.seek(0)
        command_output = output.read()

        LogEntry.objects.log_action(
            user_id=self.request.user.pk,
            content_type_id=None, object_id=None,
            object_repr=_('Data reset to %(scenario)s scenario') % {
                'scenario': scenario
            },
            action_flag=CHANGE_LOG_ENTRY,
        )
        logger.info('User "%(username)s" reset data for testing using "%(scenario)s" scenario' % {
            'username': self.request.user.username,
            'scenario': scenario,
        })
        logger.debug(command_output)

        return self.render_to_response(self.get_context_data(
            form=form,
            command_output=command_output,
        ))


class FileDownloadView(
    mixins.CreateModelMixin, viewsets.GenericViewSet
):
    queryset = FileDownload.objects.all()
    serializer_class = FileDownloadSerializer

    permission_classes = (
        IsAuthenticated, ActionsBasedPermissions, BankAdminClientIDPermissions
    )


class MissingFileDownloadView(generics.GenericAPIView):
    queryset = FileDownload.objects.all()
    action = 'list'
    permission_classes = (
        IsAuthenticated, ActionsBasedPermissions, BankAdminClientIDPermissions
    )

    def get(self, request, *args, **kwargs):
        dates = self.request.query_params.getlist('date')
        label = self.request.query_params.get('label')
        errors = []
        if not label:
            errors.append(_('"label" parameter is required'))
        if not dates:
            errors.append(_('At least one "date" parameter is required'))

        parsed_dates = []
        for date in dates:
            parsed_date = parse_date(date)
            if not parsed_date:
                errors.append(
                    _('Date "%s" could not be parsed - use YYYY-MM-DD format')
                    % date
                )
            else:
                parsed_dates.append(parsed_date)

        if errors:
            return Response(data={'errors': errors}, status=400)

        # get earliest record to avoid giving false positives for dates before
        # records began
        earliest_records = self.get_queryset().filter(label=label).order_by('date')[:1]
        if len(earliest_records):
            results = self.get_queryset().filter(
                label=label,
                date__in=parsed_dates
            ).values_list('date', flat=True)

            earliest_date = earliest_records[0].date
            if results.count() != len(parsed_dates):
                missing = []
                for parsed_date in parsed_dates:
                    if parsed_date > earliest_date and parsed_date not in results:
                        missing.append(parsed_date)
                return Response(data={'missing_dates': missing}, status=200)
        return Response(data={'missing_dates': []}, status=200)


class UpdateNOMISTokenView(AdminViewMixin, FormView):
    title = _('Update NOMIS API client token')
    template_name = 'core/nomis-token.html'
    form_class = UpdateNOMISTokenForm
    success_url = reverse_lazy('admin:core_token_changelist')
    superuser_required = True

    def get_context_data(self, **kwargs):
        context_date = super().get_context_data(**kwargs)
        context_date['opts'] = Token._meta
        try:
            token = Token.objects.get(name='nomis')
            decoded_token = UpdateNOMISTokenForm.decode_token(token.token)
            context_date['token'] = token
            context_date['token_permissions'] = '\n'.join(map(str, decoded_token.get('access', []))) \
                                                or _('None')
        except Token.DoesNotExist:
            pass
        return context_date

    def form_valid(self, form):
        Token.objects.update_or_create({
            'token': form.token_data,
            'expires': form.decoded_token.get('exp'),
        }, name='nomis')
        messages.success(self.request, _('NOMIS API client token updated'))
        return super().form_valid(form)


class DownloadPublicKeyView(AdminViewMixin, View):
    superuser_required = True

    def get(self, _):
        response = HttpResponse(settings.NOMIS_API_PUBLIC_KEY.strip(), content_type='application/octet-stream')
        response['Content-Disposition'] = 'attachment; filename="public-key.pem"'
        return response


class TokenView(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Token.objects.all()
    serializer_class = TokenSerializer
    permission_classes = (
        IsAuthenticated,
        get_client_permissions_class(CASHBOOK_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID),
        TokenPermissions,
    )
