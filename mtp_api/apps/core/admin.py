from django.contrib import admin
from django.utils.translation import ugettext_lazy as _


class DateRangeFilter(admin.FieldListFilter):
    template = 'core/admin_form_filter.html'

    def __init__(self, field, request, params, model, model_admin, field_path):
        self.field_generic = '%s__' % field_path

        self.form_fields = [
            (_('Start date'), '%s__gte' % field_path),
            (_('End date (less than)'), '%s__lt' % field_path)
        ]
        super().__init__(field, request, params, model, model_admin, field_path)

    def expected_parameters(self):
        return ['%sgte' % self.field_generic, '%slt' % self.field_generic]

    def choices(self, cl):
        saved_params = cl.params.copy()

        query_active = False
        query_params = []
        # display last entered values of query params if present
        for label, param in self.form_fields:
            initial = ''
            if param in saved_params:
                query_active = True
                initial = saved_params[param]
            query_params.append((label, param, initial))

        for k in list(saved_params):
            if k.startswith(self.field_generic):
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
