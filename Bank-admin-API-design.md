# Bank admin API

## /bank_admin/transactions/ - GET

Returns a list of all recent transactions

### Filters

**status**

Filters by the status of the transactions, accepts multiple values which will be 
OR'd.

Possible values:
- *available*: returns list of transactions that have not been locked by anyone
- *locked*: returns list of locked transactions
- *credited*: returns list of transactions credited
- *refunded* (*not implemented yet*): returns list of transactions refunded
- *refund_pending* (*not implemented yet*): returns list of transactions in pending refund

For ADI file generation, this will likely be:

?status=credited&status=refunded

For refund CSV generation, this will likely be:

?status=refund_pending

## /bank_admin/transactions/ - PATCH

Change the refund status of a list of transactions

**Data**

List of transaction elements, which must consist of the following two values:

- *id*: id of the transaction to be changed
- *refunded*: `True` if the transaction has been refunded, `False` otherwise

## /bank_admin/transactions/ - POST

Create new transactions

**Data**

List of transaction elements, which the must include the following values:

- *prisoner_number*
- *prisoner_dob*
- *amount*
- *sender_sort_code*
- *sender_account_number*
- *sender_name*
- *sender_roll_number* (optional)
- *reference*
