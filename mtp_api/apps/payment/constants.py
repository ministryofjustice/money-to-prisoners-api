from extended_choices import Choices

PAYMENT_STATUS = Choices(
    ('PENDING', 'pending', 'Pending'),
    ('FAILED', 'failed', 'Failed'),
    ('TAKEN', 'taken', 'Taken')
)
