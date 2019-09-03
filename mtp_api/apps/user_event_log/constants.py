from django.utils.translation import gettext_lazy
from extended_choices import Choices

USER_EVENT_KINDS = Choices(
    (
        'NOMS_OPS_SEARCH',
        'noms_ops_search',
        gettext_lazy('Search in Intelligence Tool')
    ),
)
