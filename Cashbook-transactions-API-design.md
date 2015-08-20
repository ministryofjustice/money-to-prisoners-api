# Cashbook transactions API

List of cashbook transactions api:
- /cashbook/transactions/
- /cashbook/transactions/actions/lock/
- /cashbook/transactions/actions/unlock/


## /cashbook/transactions/  -- GET

Returns only transactions for the prisons that the user can manage.

### Filters

**status**

Filters by the status of the transactions.

Default: no status => all transactions

Possible values:
- *available*: returns list of transactions that have not been locked by anyone
- *locked*: returns list of locked transactions
- *credited*: returns list of transactions credited

**prison**

Filters by list of prisons (in OR).

Default: all prison that the user can manage.

*Note:*
- If the user can't manage a specified prison, the related returning value will be an empty list. 

**user**

Filters by single user, list of users not allowed (to keep things simple).

Default:
- all users that can manage the prisons that the logged-in user can manage if `prison` is not passed in
- all users managing the related prisons if `prison` is passed in

*Note:*
- if `status` is not passed in, the `user` filter does not make sense at all and it won't do anything.
- if `status=available`, the `user` filter does not make sense at all and it won't do anything.
- if `user` is passed in but not `prison` and the specified user can't manage the prisons of the overall query, the endpoint will return an empty list.
- if `user` and `prison` are passed in but the the specified user can't manage the specified prison, the endpoint will return an empty list.
- if `user` and `prison` are passed in, the specified user can manage the specified prison but the logged-in user can't manage the specified prison, the endpoint will return an empty list.


## /transactions/  -- PATCH

Marks/unmarks a list of transactions as credited.

**Data**

List of:
- *id*: id of the transaction to be changed
- *credited*: `True` if the transactions has to be marked as credited, `False` otherwise

*Note:*
- returns 403 if at least one of the transactions have been locked by a different user. Only the user that locked a transaction can mark/unmark it as credited.
- returns 400 if at least one of the transactions is not locked. Transactions have to be locked before being able to get changed.


## /transactions/actions/lock/  -- POST

Locks some transactions. There's no way to specify which transactions have to be locked as the user doesn't care which one they lock.

No data has to be specified.

### Params

**count**

Number of transactions to be locked.

Default: *min(20, 20-count(locked-transactions))*. This is to make sure that the user can only lock max 20 transactions at any given time.

**prison (mandatory)**

Id of the prison to be used when locking transactions. It has to be one of the prisons that the user can manage otherwise it will error.

Default: no defaults.

*Note*:
- returns 403 if the specified `prison` is not one of the prisons that the user can manage.

**for_user** - *we don't need this for now so maybe we don't need to implement it?*

User the transactions will be assigned to.

Default: logged-in user

*Note:*

- returns 403 if `for_user` is passed in but the logged-in user and the specified user do not belong to the same specified prison.

## /transactions/actions/unlock/  -- POST

Unlocks some transactions.

## Data

**transaction_ids (mandatory)**

List of transactions to be unlocked.

*Note:*

- returns 403 if at least one of the transactions belongs to a prison not managed by the logged-in user
- returns 400 if at least one of the transactions is credited. Available transactions can be unlocked without any problems as their state will not change anyway.
