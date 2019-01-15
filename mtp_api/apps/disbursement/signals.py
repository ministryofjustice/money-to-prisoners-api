from django.dispatch import Signal

disbursement_created = Signal(providing_args=['disbursement', 'by_user'])
disbursement_edited = Signal(providing_args=['disbursement', 'by_user'])
disbursement_rejected = Signal(providing_args=['disbursement', 'by_user'])
disbursement_confirmed = Signal(providing_args=['disbursement', 'by_user'])
disbursement_sent = Signal(providing_args=['disbursement', 'by_user'])
disbursement_cancelled = Signal(providing_args=['disbursement', 'by_user'])
