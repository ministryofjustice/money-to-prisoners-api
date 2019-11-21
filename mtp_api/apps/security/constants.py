from django.utils.translation import gettext_lazy

from extended_choices import Choices

CHECK_STATUS = Choices(
    ('PENDING', 'pending', gettext_lazy('Pending')),
    ('ACCEPTED', 'accepted', gettext_lazy('Accepted')),
    ('REJECTED', 'rejected', gettext_lazy('Rejected')),
)
