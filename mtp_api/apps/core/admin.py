from django.contrib import admin
from django.contrib.admin.utils import prepare_lookup_value
from django.utils.translation import ugettext_lazy as _
from django import forms

from .forms import AdminFilterForm, SidebarDateWidget


class DateRangeFilter(admin.FieldListFilter):
    template = 'core/admin_form_filter.html'

    def __init__(self, field, request, params, model, model_admin, field_path):
        self.field_generic = '%s__' % field_path

        self.form_fields = [
            (_('Start date'), '%s__gte' % field_path),
            (_('End date'), '%s__lt' % field_path)
        ]
        super().__init__(field, request, params, model, model_admin, field_path)

    def expected_parameters(self):
        return ['%sgte' % self.field_generic, '%slt' % self.field_generic]

    def choices(self, cl):
        query_active = False

        fields_to_render = []
        for k in cl.params:
            if not k.startswith(self.field_generic):
                fields_to_render.append(
                    (k, forms.CharField(initial=cl.params[k],
                                        widget=forms.HiddenInput()))
                )

        for label, param in self.form_fields:
            initial = ''
            if param in cl.params:
                query_active = True
                initial = cl.params[param]
            fields_to_render.append(
                (param, forms.DateField(widget=SidebarDateWidget(
                    attrs={'placeholder': label}), initial=initial))
            )

        form = AdminFilterForm(extra_fields=fields_to_render)

        return [
            {
                'selected': not query_active,
                'query_string': cl.get_query_string({}, [self.field_generic]),
                'display': _('Any date')
            },
            {
                'selected': query_active,
                'form': form,
                'display': _('Date in range')
            },
        ]


class RelatedAnyFieldListFilter(admin.RelatedFieldListFilter):

    def choices(self, cl):
        from django.contrib.admin.views.main import EMPTY_CHANGELIST_VALUE
        for c in super().choices(cl):
            # alter 'selected' test for empty option as default implementation
            # does not check actual value of the argument
            if c['display'] == EMPTY_CHANGELIST_VALUE:
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
