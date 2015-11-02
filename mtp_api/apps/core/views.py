from io import StringIO

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
            'protect_superusers': True,
            'protect_transactions': False,
            'clerks_per_prison': 4,

            'no_color': True,
            'stdout': output,
            'stderr': output,
        }

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
        output.seek(0)

        return self.render_to_response(self.get_context_data(
            form=form,
            command_output=output.read(),
        ))
