from django.contrib import admin
from django.contrib.admin.utils import prepare_lookup_value
from django.utils.translation import ugettext_lazy as _
from django import forms

from .forms import AdminFilterForm, SidebarDateWidget


class FormFilter(admin.FieldListFilter):
    template = 'core/admin_form_filter.html'

    def __init__(self, field, request, params, model, model_admin, field_path):
        self.field_generic = '%s__' % field_path
        self.field_path = field_path
        super().__init__(field, request, params, model, model_admin, field_path)

    def expected_parameters(self):
        return list(next(zip(*self.get_form_fields())))

    def choices(self, cl):
        query_active = False
        fields_to_render = self.get_form_fields()

        for param, field in fields_to_render:
            if param in cl.params:
                query_active = True
                break

        for k in cl.params:
            if not (k == self.field_path or k.startswith(self.field_generic)):
                fields_to_render.append(
                    (k, forms.CharField(widget=forms.HiddenInput()))
                )

        initial = {}
        for name, field in fields_to_render:
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


class DateRangeFilter(FormFilter):

    def get_form_fields(self):
        return [
            ('%s__gte' % self.field_path, forms.DateField(
                widget=SidebarDateWidget(attrs={'placeholder': _('Start date')})
            )),
            ('%s__lt' % self.field_path, forms.DateField(
                widget=SidebarDateWidget(attrs={'placeholder': _('End date')})
            ))
        ]

    def get_submit_label(self):
        return _('Date in range')


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
