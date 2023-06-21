from django.db import models


class NotificationTarget(models.TextChoices):
    bankadmin_login = 'bankadmin_login', 'Bank admin: before login'
    bankadmin_dashboard = 'bankadmin_dashboard', 'Bank admin: dashboard'
    cashbook_login = 'cashbook_login', 'Cashbook: before login'
    cashbook_dashboard = 'cashbook_dashboard', 'Cashbook: dashboard'
    cashbook_all = 'cashbook_all', 'Cashbook: all apps'
    cashbook_cashbook = 'cashbook_cashbook', 'Cashbook: cashbook app'
    cashbook_disbursements = 'cashbook_disbursements', 'Cashbook: disbursements app'
    noms_ops_login = 'noms_ops_login', 'Noms Ops: before login'
    noms_ops_security_dashboard = 'noms_ops_security_dashboard', 'Noms Ops: security dashboard'
    send_money_landing = 'send_money_landing', 'Send Money: landing page'


class Service(models.TextChoices):
    gov_uk_pay = 'gov_uk_pay', 'GOV.UK Pay'
