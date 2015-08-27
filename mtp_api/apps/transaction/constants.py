from extended_choices import Choices


TRANSACTION_STATUS = Choices(
    # transactions with owner == None and credited == False
    ('AVAILABLE',   'available', 'Available'),

    # transactions with owner != None and credited == False
    ('LOCKED',  'locked', 'Locked'),

    # transactions with owner != None and credited == True
    ('CREDITED', 'credited', 'Credited'),
)


# max number of transactions a user can lock at any time
LOCK_LIMIT = 20


LOG_ACTIONS = Choices(
    ('CREATED', 'created', 'Created'),
    ('LOCKED', 'locked', 'Locked'),
    ('UNLOCKED', 'unlocked', 'Unlocked'),
    ('CREDITED', 'credited', 'Credited'),
    ('UNCREDITED', 'uncredited', 'Uncredited'),
)
