from django.contrib import admin
from django.utils.translation import ugettext_lazy as _


class DateRangeFilter(admin.FieldListFilter):
    template = 'core/admin_form_filter.html'

    def __init__(self, field, request, params, model, model_admin, field_path):
        self.field_generic = '%s__' % field_path
        super().__init__(field, request, params, model, model_admin, field_path)

    def expected_parameters(self):
        return ['%sgte' % self.field_generic, '%slt' % self.field_generic]

    def choices(self, cl):
        query_active = False
        saved_params = cl.params.copy()
        query_params = {k: '' for k in self.expected_parameters()}
        for k in list(saved_params):
            if k.startswith(self.field_generic):
                # display last entered values of query params if present
                if k in query_params:
                    query_active = True
                    query_params[k] = saved_params[k]
                del saved_params[k]

        return [
            {
                'selected': not query_active,
                'query_string': cl.get_query_string({}, [self.field_generic]),
                'display': _('Any date')
            },
            {
                'selected': query_active,
                'saved_params': saved_params,
                'query_params': query_params,
                'display': _('Date in range')
            },
        ]
