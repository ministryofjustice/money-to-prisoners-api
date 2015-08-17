from django.dispatch import Signal

transaction_created = Signal(providing_args=['transaction', 'by_user'])
transaction_taken = Signal(providing_args=['transaction', 'by_user'])
transaction_released = Signal(providing_args=['transaction', 'by_user'])
transaction_credited = Signal(providing_args=['transaction', 'by_user'])
