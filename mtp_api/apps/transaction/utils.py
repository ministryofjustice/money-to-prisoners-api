def format_amount(amount_pence, trim_empty_pence=False):
    """
    Format an amount in pence as pounds
    :param amount_pence: int pence amount
    :param trim_empty_pence: if True, strip off .00
    :return: str
    """
    if not isinstance(amount_pence, int):
        return ''
    pounds = amount_pence / 100
    text_amount = '£{:0,.2f}'.format(pounds)
    if trim_empty_pence and text_amount.endswith('.00'):
        text_amount = text_amount[:-3]
    return text_amount


def format_number(value):
    """
    Format a number with thousands separator
    :param value: number to format
    :return: str
    """
    return '{:,}'.format(value)
