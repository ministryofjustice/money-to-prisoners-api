from urllib.parse import urlsplit

# send-money passes prisoner numbers and dates of birth in the query string of these paths
PRISONER_DETAILS_PATHS = ('/prisoner_validity/',)


def scrub_prisoner_details(event, hint):
    """
    Sentry `before_send` hook that removes prisoner details from errors raised during prisoner validity checks:
    the query string is dropped and so are local variables, which include the request and parsed details
    """
    request = event.get('request') or {}
    # request url is not always set, e.g. outside of the wsgi middleware, but django sets the transaction to the route
    paths = (urlsplit(request.get('url') or '').path, event.get('transaction') or '')
    if not any(path.startswith(PRISONER_DETAILS_PATHS) for path in paths):
        return event

    request.pop('query_string', None)
    stacktraces = [
        value.get('stacktrace')
        for key in ('exception', 'threads')
        for value in (event.get(key) or {}).get('values') or []
    ]
    for stacktrace in filter(None, stacktraces):
        for frame in stacktrace.get('frames') or []:
            frame.pop('vars', None)
    return event
