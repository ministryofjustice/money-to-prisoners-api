from django.db import models


class Service(models.TextChoices):
    gov_uk_pay = 'gov_uk_pay', 'GOV.UK Pay'
