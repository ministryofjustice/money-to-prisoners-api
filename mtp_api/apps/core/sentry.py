from urllib.parse import parse_qsl, urlsplit

# send-money passes prisoner numbers and dates of birth in the query string of these paths
PRISONER_DETAILS_PATHS = ('/prisoner_validity/',)
PRISONER_DETAILS_PARAMS = ('prisoner_number', 'prisoner_dob')
# shorter submitted values identify no-one and replacing them would garble the rest of the event
MIN_REDACTED_LENGTH = 4


def scrub_prisoner_details(event, hint):
    """
    Sentry `before_send` hook that removes prisoner details from errors raised during prisoner validity checks:
    the query string is dropped and submitted values are replaced wherever else they appear,
    e.g. in exception messages or log entries.
    Local variables are not sent at all (`include_local_variables=False`)
    """
    request = event.get('request') or {}
    # request url is not always set, e.g. outside of the wsgi middleware, but django sets the transaction to the route
    paths = (urlsplit(request.get('url') or '').path, event.get('transaction') or '')
    if not any(path.startswith(PRISONER_DETAILS_PATHS) for path in paths):
        return event

    query_string = request.pop('query_string', None) or ''
    submitted_values = {
        value
        for key, value in parse_qsl(query_string)
        if key in PRISONER_DETAILS_PARAMS and len(value) >= MIN_REDACTED_LENGTH
    }
    if submitted_values:
        event = _redact(event, submitted_values)
    return event


def _redact(value, submitted_values):
    if isinstance(value, str):
        for submitted_value in submitted_values:
            value = value.replace(submitted_value, '[Filtered]')
        return value
    if isinstance(value, dict):
        return {key: _redact(item, submitted_values) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item, submitted_values) for item in value]
    return value
