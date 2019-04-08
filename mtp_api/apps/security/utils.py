from credit.models import Credit
from disbursement.models import Disbursement


def get_monitored_credits(user, **filters):
    bank_account_credits = Credit.objects.filter(
        sender_profile__bank_transfer_details__sender_bank_account__monitoring_users=user,
        **filters
    )
    debit_card_credits = Credit.objects.filter(
        sender_profile__debit_card_details__monitoring_users=user,
        **filters
    )
    prisoner_credits = Credit.objects.filter(
        prisoner_profile__monitoring_users=user,
        **filters
    )

    return bank_account_credits.union(debit_card_credits).union(prisoner_credits)


def get_monitored_disbursements(user, **filters):
    bank_account_credits = Disbursement.objects.filter(
        recipient_profile__bank_transfer_details__recipient_bank_account__monitoring_users=user,
        **filters
    )
    prisoner_credits = Disbursement.objects.filter(
        prisoner_profile__monitoring_users=user,
        **filters
    )

    return bank_account_credits.union(prisoner_credits)
