import django_filters


class StatusChoiceFilter(django_filters.ChoiceFilter):

    def filter(self, qs, value):
        if value:
            qs = qs.filter(**qs.model.STATUS_LOOKUP[value.lower()])
        return qs
