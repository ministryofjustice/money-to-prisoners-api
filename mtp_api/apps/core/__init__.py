import functools

_not_provided = object()


def getattr_path(obj, path, default=_not_provided):
    if isinstance(path, str):
        path = path.split('.')
    key = path.pop(0)
    value = getattr(obj, key, _not_provided)
    if value is _not_provided:
        if default is _not_provided:
            raise AttributeError
        return default
    if path:
        return getattr_path(value, path, default=default)
    return value


def dictfetchall(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def mean(iterable):
    reduced = functools.reduce(lambda previous, value: (previous[0] + 1, previous[1] + value),
                               iterable, (0, 0))
    if reduced[0] == 0:
        return float('nan')
    return reduced[1] / reduced[0]
