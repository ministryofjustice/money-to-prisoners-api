import datetime


def monday_of_same_week(date: datetime.date) -> datetime.date:
    """
    Returns the Monday of the same week as date

    How it works: datetime.date.weekday() returns 0 for Monday, 1 for Tuesday
    and so on. So effectively it's the number of days you need to go back in
    order to return to Monday.
    """

    monday = date - datetime.timedelta(days=date.weekday())
    return monday
