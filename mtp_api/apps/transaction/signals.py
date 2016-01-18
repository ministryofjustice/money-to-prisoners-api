from django.dispatch import Signal

transaction_created = Signal(providing_args=['transaction', 'by_user'])
transaction_locked = Signal(providing_args=['transaction', 'by_user'])
transaction_unlocked = Signal(providing_args=['transaction', 'by_user'])
transaction_credited = Signal(providing_args=['transaction', 'by_user'])
transaction_refunded = Signal(providing_args=['transaction', 'by_user'])
transaction_reconciled = Signal(providing_args=['transaction', 'by_user'])
transaction_payment_taken = Signal(providing_args=['transaction', 'by_user'])
transaction_payment_failed = Signal(providing_args=['transaction', 'by_user'])

transaction_prisons_need_updating = Signal()
