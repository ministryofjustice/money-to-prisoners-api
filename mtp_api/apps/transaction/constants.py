from extended_choices import Choices


TRANSACTION_STATUS = Choices(
    # transactions with owner != None and credited == False
    ('PENDING',  'pending', 'Pending'),

    # transactions with owner == None and credited == False
    ('AVAILABLE',   'available', 'Available'),

    # transactions with owner != None and credited == True
    ('CREDITED', 'credited', 'Credited'),
)
