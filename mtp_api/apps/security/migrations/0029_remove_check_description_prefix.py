from django.db import migrations
from django.db.models import Value
from django.db.models.functions import Concat, Substr

PREFIX = 'Credit matched: '


def get_checks_with_matched_rules(apps):
    """
    Get all checks that matched at least one rule and did not have the old hard-coded description
    """
    check_cls = apps.get_model('security', 'Check')
    checks_with_matched_rules = check_cls.objects \
        .exclude(rules=[]) \
        .exclude(description='Credit matched FIU monitoring rules')
    return checks_with_matched_rules


def remove_check_description_prefix(apps, schema_editor):
    checks_with_matched_rules = get_checks_with_matched_rules(apps)
    checks_with_matched_rules.update(description=Substr('description', len(PREFIX) + 1))


def add_check_description_prefix(apps, schema_editor):
    checks_with_matched_rules = get_checks_with_matched_rules(apps)
    checks_with_matched_rules.update(description=Concat(Value(PREFIX), 'description'))


class Migration(migrations.Migration):
    dependencies = [
        ('security', '0028_auto_20200624_1547'),
    ]
    operations = [
        migrations.RunPython(code=remove_check_description_prefix, reverse_code=add_check_description_prefix),
    ]
