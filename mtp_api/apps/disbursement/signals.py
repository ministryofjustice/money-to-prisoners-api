from django.dispatch import Signal

# providing_args=['disbursement', 'by_user']
disbursement_created = Signal()
# providing_args=['disbursement', 'by_user']
disbursement_edited = Signal()
# providing_args=['disbursement', 'by_user']
disbursement_rejected = Signal()
# providing_args=['disbursement', 'by_user']
disbursement_confirmed = Signal()
# providing_args=['disbursement', 'by_user']
disbursement_sent = Signal()
