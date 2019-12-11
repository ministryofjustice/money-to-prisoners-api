from django.dispatch import Signal

credit_created = Signal(providing_args=['credit', 'by_user'])
credit_credited = Signal(providing_args=['credit', 'by_user'])
credit_refunded = Signal(providing_args=['credit', 'by_user'])
credit_reconciled = Signal(providing_args=['credit', 'by_user'])
credit_reviewed = Signal(providing_args=['credit', 'by_user'])
credit_set_manual = Signal(providing_args=['credit', 'by_user'])
credit_failed = Signal(providing_args=['credit'])

credit_prisons_need_updating = Signal()
