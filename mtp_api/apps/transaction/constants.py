from extended_choices import Choices


TRANSACTION_STATUS = Choices(
    # transactions with owner != None and credited == False
    ('PENDING',  'pending', 'Pending'),

    # transactions with owner == None and credited == False
    ('AVAILABLE',   'available', 'Available'),

    # transactions with owner != None and credited == True
    ('CREDITED', 'credited', 'Credited'),
)


# max number of transactions a user can take at any time
# this only refers to pending transactions
TAKE_LIMIT = 20
DEFAULT_SLICE_SIZE = TAKE_LIMIT
