from mtp_common.spooling import spoolable

from notification.rules import ENABLED_RULE_CODES, RULES


@spoolable(body_params=['records'])
def create_notification_events(records):
    for record in records:
        for code in ENABLED_RULE_CODES:
            rule = RULES[code]
            if rule.applies_to(record) and rule.triggered(record):
                rule.create_events(record)
