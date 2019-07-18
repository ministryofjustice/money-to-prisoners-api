import math


def format_amount(
    amount_pence, trim_empty_pence=False, truncate_after=None, pound_sign=True
):
    """
    Format an amount in pence as pounds
    :param amount_pence: int pence amount
    :param trim_empty_pence: if True, strip off .00
    :param truncate_after: if a number of pounds, will round into £1k, £15m format above this amount
    :param pound_sign: whether to prefix with £
    :return: str
    """
    text_amount = ''
    if not isinstance(amount_pence, int):
        return text_amount

    pounds = math.fabs(amount_pence / 100)
    if truncate_after is not None and pounds >= truncate_after:
        if pounds >= 1000000:
            text_amount = '{:0,.1f}m'.format(pounds / 1000000)
        if pounds >= 1000:
            text_amount = '{:0,.1f}k'.format(pounds / 1000)
    else:
        text_amount = '{:0,.2f}'.format(pounds)
        if trim_empty_pence and text_amount.endswith('.00'):
            text_amount = text_amount[:-3]
    if pound_sign:
        text_amount = f'£{text_amount}'
    if amount_pence < 0:
        text_amount = f'-{text_amount}'
    return text_amount


def format_number(value, truncate_after=None):
    """
    Format a number with thousands separator
    :param value: number to format
    :param truncate_after: if a number, will round into 1k, 15m format above this
    :return: str
    """
    if truncate_after is not None and value > truncate_after:
        if value >= 1000000:
            return '{:,}m'.format(value / 1000000)
        if value >= 1000:
            return '{:,}k'.format(value / 1000)
    return '{:,}'.format(value)


def format_percentage(number):
    """
    Formats a number into a percentage string
    :param number: a number assumed to be between 0 and 1
    :return: str
    """
    return '{}%'.format(round(number * 100))
