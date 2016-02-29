from io import StringIO
import logging

from django.conf import settings
from django.contrib.admin import site
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.urlresolvers import reverse_lazy
from django.http.response import Http404
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from .forms import RecreateTestDataForm

logger = logging.getLogger('mtp')


class RecreateTestDataView(FormView):
    """
    Django admin view which calls load_test_data management command
    """
    form_class = RecreateTestDataForm
    template_name = 'core/recreate_test_data.html'
    success_url = reverse_lazy('mtp-admin:recreate_test_data')

    @method_decorator(site.admin_view)
    def dispatch(self, request, *args, **kwargs):
        if settings.ENVIRONMENT == 'prod':
            raise Http404
        if not request.user.is_superuser:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'title': _('Recreate test data'),
        })
        return context

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
